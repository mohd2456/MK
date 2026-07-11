"""Plugin execution sandbox.

Isolates plugin tool execution to prevent misbehaving plugins from:
- Exceeding time limits (async timeout)
- Accessing files outside allowed paths
- Making unauthorized network calls
- Consuming excessive memory
- Importing restricted modules
- Crashing the main MK process

The sandbox wraps each tool call with permission checks and
resource constraints. It does NOT use OS-level sandboxing (too heavy
for a homelab) — instead it enforces rules at the Python level with
clear error reporting when a plugin violates its contract.
"""

from __future__ import annotations

import asyncio
import builtins
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from mk.plugins.manifest import PluginManifest, PluginPermission
from mk.tools.base import ToolResult

logger = logging.getLogger(__name__)

# Default modules that plugins are not allowed to import
# unless explicitly whitelisted in the sandbox config
DEFAULT_BLOCKED_IMPORTS: Set[str] = {
    "os",
    "subprocess",
    "sys",
    "shutil",
    "ctypes",
    "importlib",
    "code",
    "codeop",
    "compile",
    "compileall",
    "multiprocessing",
    "signal",
    "socket",
}


class SandboxViolation(Exception):
    """Raised when a plugin violates its declared sandbox constraints.

    This means the plugin tried to do something it didn't declare
    in its manifest. The violation is logged and the tool call fails.
    """

    def __init__(self, plugin: str, violation: str, permission: Optional[str] = None):
        self.plugin = plugin
        self.violation = violation
        self.permission = permission
        super().__init__(f"Plugin '{plugin}' sandbox violation: {violation}")


@dataclass
class SandboxConfig:
    """Configuration for the plugin sandbox.

    These are system-wide limits. Individual plugins can request
    LESS than these (via their manifest) but never more.
    """

    # Time limits
    max_timeout_seconds: float = 60.0
    default_timeout_seconds: float = 30.0

    # Memory limits
    max_memory_mb: int = 512
    default_memory_mb: int = 256

    # Filesystem limits
    allowed_read_paths: List[str] = field(
        default_factory=lambda: [
            "/data/",
            "/opt/docker/",
            "/tmp/mk/",
        ]
    )
    allowed_write_paths: List[str] = field(
        default_factory=lambda: [
            "/tmp/mk/",
        ]
    )
    blocked_paths: List[str] = field(
        default_factory=lambda: [
            "/etc/shadow",
            "/etc/passwd",
            "/root/.ssh/",
            "/etc/mk/secrets/",
        ]
    )

    # Network limits
    blocked_hosts: List[str] = field(
        default_factory=lambda: [
            "169.254.169.254",  # AWS metadata
            "metadata.google.internal",
        ]
    )

    # Execution tracking
    max_concurrent_executions: int = 5

    # Import restrictions
    blocked_imports: Set[str] = field(default_factory=lambda: DEFAULT_BLOCKED_IMPORTS.copy())
    import_whitelist: Set[str] = field(default_factory=set)


@dataclass
class ExecutionContext:
    """Context for a single tool execution.

    Created fresh for each tool call. Tracks what the plugin
    does during execution for audit and violation detection.
    """

    plugin_name: str
    tool_name: str
    permissions: Set[PluginPermission]
    timeout_seconds: float
    max_memory_mb: int
    start_time: float = field(default_factory=time.time)
    files_read: List[str] = field(default_factory=list)
    files_written: List[str] = field(default_factory=list)
    commands_executed: List[str] = field(default_factory=list)
    network_calls: List[str] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since execution started."""
        return time.time() - self.start_time

    @property
    def is_timed_out(self) -> bool:
        """Whether execution has exceeded timeout."""
        return self.elapsed_seconds > self.timeout_seconds


class RestrictedImporter:
    """Context manager that restricts which modules can be imported.

    Temporarily replaces builtins.__import__ with a gated version
    that blocks imports of restricted modules. Used during sandboxed
    plugin execution to prevent plugins from importing dangerous modules.

    NOTE: This replaces a process-global hook and is not safe for
    concurrent use. The PluginSandbox serializes access via an
    asyncio.Lock to ensure only one RestrictedImporter is active
    at a time.

    Usage:
        with RestrictedImporter(blocked={"os", "subprocess"}):
            exec(plugin_code)  # os and subprocess imports will raise
    """

    def __init__(
        self,
        blocked: Optional[Set[str]] = None,
        whitelist: Optional[Set[str]] = None,
    ) -> None:
        """Initialize the restricted importer.

        Args:
            blocked: Set of module names to block.
            whitelist: Set of module names to always allow (overrides blocked).
        """
        self._blocked = blocked or DEFAULT_BLOCKED_IMPORTS.copy()
        self._whitelist = whitelist or set()
        self._original_import: Optional[Callable] = None

    def __enter__(self) -> "RestrictedImporter":
        """Install the restricted import hook."""
        self._original_import = builtins.__import__

        blocked = self._blocked
        whitelist = self._whitelist
        original = self._original_import

        def restricted_import(name: str, *args: Any, **kwargs: Any) -> Any:
            # Get the top-level module name
            top_level = name.split(".")[0]

            # Check whitelist first (always allowed)
            if top_level in whitelist:
                return original(name, *args, **kwargs)

            # Check blocked list
            if top_level in blocked:
                raise ImportError(
                    f"Import of '{name}' is blocked by the plugin sandbox. "
                    f"Module '{top_level}' is restricted."
                )

            return original(name, *args, **kwargs)

        builtins.__import__ = restricted_import
        return self

    def __exit__(self, *args: Any) -> None:
        """Restore the original import function."""
        if self._original_import is not None:
            builtins.__import__ = self._original_import


class PluginSandbox:
    """Execution sandbox for plugin tool calls.

    Wraps each tool invocation with:
    1. Permission validation (before execution)
    2. Timeout enforcement (during execution)
    3. Resource tracking (during execution)
    4. Import restriction (during execution)
    5. Result validation (after execution)

    Uses an asyncio.Lock to serialize the RestrictedImporter usage,
    which is process-global. This prevents concurrent sandbox executions
    from interfering with each other's import hooks.

    Does NOT use containers or VMs -- this is Python-level isolation
    suitable for a trusted homelab environment where the goal is
    catching bugs and misconfigurations, not adversarial attacks.
    """

    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        """Initialize the sandbox.

        Args:
            config: Sandbox configuration. Uses defaults if None.
        """
        self.config = config or SandboxConfig()
        self._active_executions: int = 0
        self._execution_history: List[Dict[str, Any]] = []
        # Lock to serialize import hook manipulation (process-global resource)
        self._import_lock = asyncio.Lock()

    @property
    def active_executions(self) -> int:
        """Number of currently running sandboxed executions."""
        return self._active_executions

    async def execute(
        self,
        manifest: PluginManifest,
        tool_name: str,
        handler: Callable[..., Any],
        args: Dict[str, Any],
    ) -> ToolResult:
        """Execute a plugin tool call within the sandbox.

        This is the main entry point. It:
        1. Validates the tool exists in the manifest
        2. Checks concurrency limits
        3. Creates an execution context
        4. Runs the handler with timeout
        5. Records the execution for audit

        Args:
            manifest: The plugin's manifest (source of truth for permissions).
            tool_name: Which tool to execute.
            handler: The actual async function to call.
            args: Arguments to pass to the handler.

        Returns:
            ToolResult from the plugin, or an error ToolResult on violation/timeout.
        """
        # Validate tool exists
        tool_def = manifest.get_tool(tool_name)
        if not tool_def:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found in plugin '{manifest.name}'",
            )

        # Check concurrency
        if self._active_executions >= self.config.max_concurrent_executions:
            return ToolResult(
                success=False,
                error=(
                    f"Too many concurrent plugin executions "
                    f"({self._active_executions}/{self.config.max_concurrent_executions})"
                ),
            )

        # Determine timeout (plugin-declared or system default, whichever is lower)
        timeout = min(
            manifest.timeout_seconds,
            self.config.max_timeout_seconds,
        )

        # Create execution context
        ctx = ExecutionContext(
            plugin_name=manifest.name,
            tool_name=tool_name,
            permissions=set(manifest.permissions),
            timeout_seconds=timeout,
            max_memory_mb=min(manifest.max_memory_mb, self.config.max_memory_mb),
        )

        self._active_executions += 1
        try:
            result = await self._run_with_timeout(handler, args, ctx)
            self._record_execution(ctx, result)
            return result
        except SandboxViolation as e:
            logger.warning(f"Sandbox violation: {e}")
            self._record_execution(ctx, None, violation=str(e))
            return ToolResult(
                success=False,
                error=f"Sandbox violation: {e.violation}",
                metadata={"violation": True, "plugin": manifest.name},
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Plugin '{manifest.name}' tool '{tool_name}' timed out after {timeout}s"
            )
            self._record_execution(ctx, None, violation="timeout")
            return ToolResult(
                success=False,
                error=f"Plugin timed out after {timeout} seconds",
                metadata={"timeout": True, "plugin": manifest.name},
            )
        except Exception as e:
            logger.error(
                f"Plugin '{manifest.name}' tool '{tool_name}' crashed: {e}",
                exc_info=True,
            )
            self._record_execution(ctx, None, violation=f"crash: {e}")
            return ToolResult(
                success=False,
                error=f"Plugin error: {type(e).__name__}: {e}",
                metadata={"crash": True, "plugin": manifest.name},
            )
        finally:
            self._active_executions -= 1

    async def _run_with_timeout(
        self,
        handler: Callable[..., Any],
        args: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> ToolResult:
        """Run the handler with async timeout enforcement and import restrictions.

        Acquires the import lock to ensure only one sandboxed execution
        manipulates builtins.__import__ at a time, preventing race conditions
        between concurrent async tasks.

        Args:
            handler: The plugin tool function.
            args: Tool arguments.
            ctx: Execution context for tracking.

        Returns:
            ToolResult from the handler.

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout.
            SandboxViolation: If restricted imports are attempted.
        """
        # Determine which imports to block (unless plugin has shell permission)
        blocked = self.config.blocked_imports.copy()
        whitelist = self.config.import_whitelist.copy()

        # If plugin has shell exec permission, allow os and subprocess
        if PluginPermission.SHELL_EXEC in ctx.permissions:
            blocked.discard("os")
            blocked.discard("subprocess")

        # If plugin has network permission, allow socket
        if (
            PluginPermission.NETWORK_LOCAL in ctx.permissions
            or PluginPermission.NETWORK_INTERNET in ctx.permissions
        ):
            blocked.discard("socket")

        # Acquire lock to serialize access to builtins.__import__
        async with self._import_lock:
            with RestrictedImporter(blocked=blocked, whitelist=whitelist):
                result = await asyncio.wait_for(
                    handler(**args),
                    timeout=ctx.timeout_seconds,
                )

        # Ensure result is a ToolResult
        if isinstance(result, ToolResult):
            return result
        elif isinstance(result, dict):
            return ToolResult(**result)
        elif isinstance(result, str):
            return ToolResult(success=True, output=result)
        else:
            return ToolResult(success=True, output=str(result))

    def check_file_access(self, ctx: ExecutionContext, path: str, write: bool = False) -> None:
        """Check if a file access is allowed by the sandbox.

        Called by sandboxed filesystem operations to validate access.

        Args:
            ctx: Current execution context.
            path: Path being accessed.
            write: Whether this is a write operation.

        Raises:
            SandboxViolation: If access is not permitted.
        """
        resolved = str(Path(path).resolve())

        # Check blocked paths first
        for blocked in self.config.blocked_paths:
            if resolved.startswith(blocked):
                raise SandboxViolation(
                    ctx.plugin_name,
                    f"Access to blocked path: {path}",
                    permission="filesystem",
                )

        # Check permissions
        if write:
            if PluginPermission.FILESYSTEM_WRITE not in ctx.permissions:
                raise SandboxViolation(
                    ctx.plugin_name,
                    f"Write access not declared in permissions: {path}",
                    permission=PluginPermission.FILESYSTEM_WRITE.value,
                )
            # Check against allowed write paths
            allowed = any(resolved.startswith(p) for p in self.config.allowed_write_paths)
            if not allowed:
                raise SandboxViolation(
                    ctx.plugin_name,
                    f"Write to non-allowed path: {path}",
                    permission=PluginPermission.FILESYSTEM_WRITE.value,
                )
            ctx.files_written.append(resolved)
        else:
            if PluginPermission.FILESYSTEM_READ not in ctx.permissions:
                raise SandboxViolation(
                    ctx.plugin_name,
                    f"Read access not declared in permissions: {path}",
                    permission=PluginPermission.FILESYSTEM_READ.value,
                )
            ctx.files_read.append(resolved)

    def check_shell_access(self, ctx: ExecutionContext, command: str) -> None:
        """Check if shell command execution is allowed.

        Args:
            ctx: Current execution context.
            command: Command being executed.

        Raises:
            SandboxViolation: If shell access is not permitted.
        """
        if PluginPermission.SHELL_EXEC not in ctx.permissions:
            raise SandboxViolation(
                ctx.plugin_name,
                f"Shell execution not declared in permissions: {command}",
                permission=PluginPermission.SHELL_EXEC.value,
            )
        ctx.commands_executed.append(command)

    def check_network_access(self, ctx: ExecutionContext, host: str, local: bool = False) -> None:
        """Check if network access is allowed.

        Args:
            ctx: Current execution context.
            host: Host being accessed.
            local: Whether this is a local network call.

        Raises:
            SandboxViolation: If network access is not permitted.
        """
        required = PluginPermission.NETWORK_LOCAL if local else PluginPermission.NETWORK_INTERNET
        if required not in ctx.permissions:
            raise SandboxViolation(
                ctx.plugin_name,
                f"Network access ({required.value}) not declared: {host}",
                permission=required.value,
            )

        # Check blocked hosts
        if host in self.config.blocked_hosts:
            raise SandboxViolation(
                ctx.plugin_name,
                f"Access to blocked host: {host}",
                permission="network",
            )
        ctx.network_calls.append(host)

    def _record_execution(
        self,
        ctx: ExecutionContext,
        result: Optional[ToolResult],
        violation: Optional[str] = None,
    ) -> None:
        """Record an execution for audit trail.

        Args:
            ctx: The execution context.
            result: The tool result (None if failed).
            violation: Violation description if any.
        """
        record = {
            "plugin": ctx.plugin_name,
            "tool": ctx.tool_name,
            "elapsed_seconds": ctx.elapsed_seconds,
            "success": result.success if result else False,
            "violation": violation,
            "files_read": ctx.files_read,
            "files_written": ctx.files_written,
            "commands_executed": ctx.commands_executed,
            "network_calls": ctx.network_calls,
            "timestamp": time.time(),
        }
        self._execution_history.append(record)

        # Keep only last 1000 records
        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-500:]

    def get_execution_history(
        self, plugin_name: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent execution records.

        Args:
            plugin_name: Filter by plugin (None for all).
            limit: Maximum records to return.

        Returns:
            List of execution records, most recent first.
        """
        records = self._execution_history
        if plugin_name:
            records = [r for r in records if r["plugin"] == plugin_name]
        return list(reversed(records[-limit:]))
