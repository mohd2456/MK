"""Plugin manager — full lifecycle orchestration.

The PluginManager is the top-level interface for the plugin system.
It coordinates loading, unloading, reloading, execution, and
file-watching for hot-reload. This is what the MK Engine uses.

Responsibilities:
- Load all plugins on startup
- Provide tool execution by qualified name (plugin.tool)
- Hot-reload plugins when files change
- Generate tool descriptions for LLM prompts
- Track plugin health and execution stats
- Bridge between the new plugin system and the existing ToolRegistry
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mk.plugins.loader import LoadedPlugin, PluginLoader
from mk.plugins.sandbox import PluginSandbox, SandboxConfig
from mk.tools.base import ToolResult

logger = logging.getLogger(__name__)


class PluginManager:
    """Orchestrates the full plugin lifecycle.

    This is the single entry point for all plugin operations:
    - Discovery and loading
    - Sandboxed execution
    - Hot-reload on file changes
    - Tool listing for LLM prompts
    - Health monitoring

    The PluginManager is designed to coexist with the existing
    ToolRegistry. Plugins loaded here can be registered into
    the registry for backward compatibility, or accessed directly.
    """

    def __init__(
        self,
        plugin_dirs: Optional[List[str]] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        auto_reload: bool = True,
    ) -> None:
        """Initialize the plugin manager.

        Args:
            plugin_dirs: Directories to scan for plugins.
            sandbox_config: Sandbox configuration.
            auto_reload: Whether to watch for file changes.
        """
        self._loader = PluginLoader(plugin_dirs)
        self._sandbox = PluginSandbox(sandbox_config)
        self._auto_reload = auto_reload

        # Plugin storage
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._file_mtimes: Dict[str, float] = {}

        # Stats
        self._total_executions: int = 0
        self._total_errors: int = 0
        self._started_at: Optional[float] = None

    @property
    def plugin_count(self) -> int:
        """Number of loaded plugins."""
        return len(self._plugins)

    @property
    def loaded_plugins(self) -> List[LoadedPlugin]:
        """All currently loaded plugins."""
        return list(self._plugins.values())

    @property
    def all_tool_names(self) -> List[str]:
        """All qualified tool names across all plugins (plugin.tool)."""
        names: List[str] = []
        for plugin in self._plugins.values():
            for tool_name in plugin.tool_names:
                names.append(f"{plugin.name}.{tool_name}")
        return names

    async def load_all(self) -> Dict[str, LoadedPlugin]:
        """Discover and load all plugins.

        Returns:
            Dict of plugin_name -> LoadedPlugin for all loaded plugins.
        """
        self._started_at = time.time()
        loaded = self._loader.load_all()

        for plugin in loaded:
            if plugin.manifest.enabled:
                self._plugins[plugin.name] = plugin
                self._track_file_mtimes(plugin)
            else:
                logger.info(f"Plugin '{plugin.name}' is disabled, skipping")

        logger.info(
            f"Plugin manager started: {len(self._plugins)} plugins, "
            f"{len(self.all_tool_names)} tools"
        )
        return dict(self._plugins)

    def load_plugin(self, plugin_path: Path) -> Optional[LoadedPlugin]:
        """Load a single plugin by path.

        Useful for loading a newly-added plugin without restarting.

        Args:
            plugin_path: Path to the plugin directory.

        Returns:
            The loaded plugin, or None if loading failed.
        """
        try:
            plugin = self._loader.load_plugin(plugin_path)
            if plugin.manifest.enabled:
                self._plugins[plugin.name] = plugin
                self._track_file_mtimes(plugin)
                return plugin
        except Exception as e:
            logger.error(f"Failed to load plugin at {plugin_path}: {e}")
        return None

    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin by name.

        Args:
            name: Plugin name to unload.

        Returns:
            True if the plugin was found and unloaded.
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Plugin '{name}' unloaded")
            return True
        return False

    async def reload_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Reload a plugin (hot-reload).

        Re-reads the manifest and module from disk.

        Args:
            name: Plugin name to reload.

        Returns:
            The reloaded plugin, or None if reload failed.
        """
        if name not in self._plugins:
            logger.warning(f"Cannot reload unknown plugin: {name}")
            return None

        old_plugin = self._plugins[name]
        try:
            new_plugin = self._loader.reload_plugin(old_plugin)
            self._plugins[name] = new_plugin
            self._track_file_mtimes(new_plugin)
            logger.info(f"Plugin '{name}' reloaded successfully")
            return new_plugin
        except Exception as e:
            logger.error(f"Failed to reload plugin '{name}': {e}")
            return None

    async def execute(
        self,
        plugin_name: str,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Execute a plugin tool in the sandbox.

        This is the main execution entry point. It:
        1. Resolves the plugin and tool
        2. Gets the handler function
        3. Runs it through the sandbox with timeout + permissions

        Args:
            plugin_name: Name of the plugin.
            tool_name: Name of the tool within the plugin.
            args: Arguments to pass to the tool.

        Returns:
            ToolResult from the sandboxed execution.
        """
        args = args or {}
        self._total_executions += 1

        # Resolve plugin
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            self._total_errors += 1
            return ToolResult(
                success=False,
                error=f"Plugin '{plugin_name}' not found. "
                f"Available: {', '.join(self._plugins.keys())}",
            )

        # Resolve handler
        handler = plugin.get_handler(tool_name)
        if not handler:
            self._total_errors += 1
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found in plugin '{plugin_name}'. "
                f"Available: {', '.join(plugin.tool_names)}",
            )

        # Execute in sandbox
        result = await self._sandbox.execute(
            manifest=plugin.manifest,
            tool_name=tool_name,
            handler=handler,
            args=args,
        )

        if not result.success:
            self._total_errors += 1

        return result

    async def execute_qualified(
        self, qualified_name: str, args: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute a tool by its qualified name (plugin.tool).

        Convenience method that parses "plugin_name.tool_name" format.

        Args:
            qualified_name: "plugin_name.tool_name" string.
            args: Arguments to pass to the tool.

        Returns:
            ToolResult from execution.
        """
        parts = qualified_name.split(".", 1)
        if len(parts) != 2:
            return ToolResult(
                success=False,
                error=f"Invalid qualified name '{qualified_name}'. "
                "Expected format: 'plugin_name.tool_name'",
            )
        return await self.execute(parts[0], parts[1], args)

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by name.

        Args:
            name: Plugin name.

        Returns:
            LoadedPlugin or None.
        """
        return self._plugins.get(name)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for all plugins (for LLM prompts).

        Returns a list of tool definitions suitable for inclusion
        in the LLM's available tools. Uses qualified names to avoid
        collisions between plugins.

        Returns:
            List of tool definition dicts.
        """
        definitions: List[Dict[str, Any]] = []

        for plugin in self._plugins.values():
            for tool_def in plugin.manifest.tools:
                definitions.append(
                    {
                        "name": f"{plugin.name}.{tool_def.name}",
                        "description": f"[{plugin.name}] {tool_def.description}",
                        "parameters": tool_def.parameters,
                        "dangerous": tool_def.dangerous,
                    }
                )

        return definitions

    def get_tools_prompt(self) -> str:
        """Generate a formatted prompt describing all plugin tools.

        Returns:
            Formatted string for LLM system prompt.
        """
        if not self._plugins:
            return ""

        lines = ["## Plugin Tools:"]
        for plugin in self._plugins.values():
            lines.append(f"\n### {plugin.name} — {plugin.manifest.description}")
            for tool_def in plugin.manifest.tools:
                dangerous_mark = " ⚠️" if tool_def.dangerous else ""
                lines.append(
                    f"  - **{plugin.name}.{tool_def.name}**{dangerous_mark}: {tool_def.description}"
                )

        return "\n".join(lines)

    async def check_for_changes(self) -> List[str]:
        """Check if any plugin files have changed on disk.

        Compares file modification times against stored values.
        Returns names of plugins that need reloading.

        Returns:
            List of plugin names with file changes.
        """
        changed: List[str] = []

        for plugin in self._plugins.values():
            if self._has_changed(plugin):
                changed.append(plugin.name)

        return changed

    async def reload_changed(self) -> List[str]:
        """Check for changes and reload any modified plugins.

        Returns:
            List of plugin names that were reloaded.
        """
        changed = await self.check_for_changes()
        reloaded: List[str] = []

        for name in changed:
            result = await self.reload_plugin(name)
            if result:
                reloaded.append(name)

        if reloaded:
            logger.info(f"Hot-reloaded {len(reloaded)} plugins: {reloaded}")

        return reloaded

    def get_status(self) -> Dict[str, Any]:
        """Get overall plugin system status.

        Returns:
            Dict with plugin count, health, execution stats.
        """
        healthy = sum(1 for p in self._plugins.values() if p.is_healthy)
        unhealthy = len(self._plugins) - healthy

        return {
            "total_plugins": len(self._plugins),
            "healthy_plugins": healthy,
            "unhealthy_plugins": unhealthy,
            "total_tools": len(self.all_tool_names),
            "total_executions": self._total_executions,
            "total_errors": self._total_errors,
            "error_rate": (
                self._total_errors / self._total_executions if self._total_executions > 0 else 0.0
            ),
            "uptime_seconds": (time.time() - self._started_at if self._started_at else 0.0),
            "plugins": {
                name: {
                    "version": p.manifest.version,
                    "tools": p.tool_names,
                    "healthy": p.is_healthy,
                    "errors": p.load_errors,
                }
                for name, p in self._plugins.items()
            },
        }

    def create_tool_executor(self) -> Callable:
        """Create a tool executor function compatible with AgentLoop.

        Returns an async callable that the agent loop can use to
        execute plugin tools by qualified name.

        Returns:
            Async function matching the tool_executor signature.
        """

        async def executor(name: str, args: Dict[str, Any]) -> Any:
            """Execute a plugin tool by name.

            Handles both qualified (plugin.tool) and unqualified names.
            For unqualified names, searches all plugins.
            """
            if "." in name:
                result = await self.execute_qualified(name, args)
            else:
                # Search for the tool across all plugins
                result = await self._execute_unqualified(name, args)
            return result

        return executor

    async def _execute_unqualified(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """Execute a tool by unqualified name (searches all plugins).

        Args:
            tool_name: Tool name without plugin prefix.
            args: Tool arguments.

        Returns:
            ToolResult from the first matching plugin.
        """
        for plugin in self._plugins.values():
            if tool_name in plugin.tool_names:
                return await self.execute(plugin.name, tool_name, args)

        return ToolResult(
            success=False,
            error=f"Tool '{tool_name}' not found in any loaded plugin",
        )

    def _track_file_mtimes(self, plugin: LoadedPlugin) -> None:
        """Record file modification times for change detection.

        Args:
            plugin: The plugin to track files for.
        """
        key = plugin.name
        files_to_track = [
            plugin.path / "plugin.yaml",
            plugin.path / "plugin.yml",
            plugin.path / "tools.py",
            plugin.path / "tools" / "__init__.py",
        ]

        max_mtime = 0.0
        for f in files_to_track:
            if f.exists():
                mtime = f.stat().st_mtime
                max_mtime = max(max_mtime, mtime)

        self._file_mtimes[key] = max_mtime

    def _has_changed(self, plugin: LoadedPlugin) -> bool:
        """Check if a plugin's files have been modified.

        Args:
            plugin: The plugin to check.

        Returns:
            True if any tracked file has a newer mtime.
        """
        key = plugin.name
        stored_mtime = self._file_mtimes.get(key, 0.0)

        files_to_check = [
            plugin.path / "plugin.yaml",
            plugin.path / "plugin.yml",
            plugin.path / "tools.py",
            plugin.path / "tools" / "__init__.py",
        ]

        for f in files_to_check:
            if f.exists():
                current_mtime = f.stat().st_mtime
                if current_mtime > stored_mtime:
                    return True

        return False
