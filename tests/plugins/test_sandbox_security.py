"""Tests for plugin sandbox security features.

Tests resource limits (timeout enforcement), import restrictions,
and permission validation.
"""

from __future__ import annotations

import asyncio

import pytest

from mk.plugins.manifest import PluginManifest, PluginPermission, PluginTool
from mk.plugins.sandbox import (
    DEFAULT_BLOCKED_IMPORTS,
    ExecutionContext,
    PluginSandbox,
    RestrictedImporter,
    SandboxConfig,
    SandboxViolation,
)
from mk.tools.base import ToolResult


def _make_manifest(
    name: str = "test-plugin",
    permissions: list | None = None,
    timeout: float = 30.0,
    tools: list | None = None,
) -> PluginManifest:
    """Helper to create a plugin manifest for tests."""
    return PluginManifest(
        name=name,
        description="Test plugin for sandbox tests",
        permissions=permissions or [],
        timeout_seconds=timeout,
        tools=tools
        or [
            PluginTool(name="test_tool", description="A test tool"),
        ],
    )


class TestExecutionTimeout:
    """Test that the sandbox enforces execution time limits."""

    async def test_fast_execution_succeeds(self) -> None:
        """A tool that completes within timeout succeeds."""
        sandbox = PluginSandbox(SandboxConfig(max_timeout_seconds=5.0))
        manifest = _make_manifest(timeout=5.0)

        async def fast_handler() -> ToolResult:
            return ToolResult(success=True, output="done")

        result = await sandbox.execute(manifest, "test_tool", fast_handler, {})
        assert result.success is True
        assert result.output == "done"

    async def test_slow_execution_times_out(self) -> None:
        """A tool that exceeds timeout returns a timeout error."""
        sandbox = PluginSandbox(SandboxConfig(max_timeout_seconds=0.5))
        manifest = _make_manifest(timeout=0.5)

        async def slow_handler() -> ToolResult:
            await asyncio.sleep(5.0)
            return ToolResult(success=True, output="should not reach")

        result = await sandbox.execute(manifest, "test_tool", slow_handler, {})
        assert result.success is False
        assert "timed out" in result.error.lower()
        assert result.metadata.get("timeout") is True

    async def test_timeout_uses_minimum_of_manifest_and_config(self) -> None:
        """Timeout is the minimum of the manifest and config values."""
        sandbox = PluginSandbox(SandboxConfig(max_timeout_seconds=1.0))
        # Plugin requests 0.3s, config allows 1.0s, so 0.3s should be used
        manifest = _make_manifest(timeout=0.3)

        async def medium_handler() -> ToolResult:
            await asyncio.sleep(0.5)  # Exceeds 0.3s but not 1.0s
            return ToolResult(success=True, output="should not reach")

        result = await sandbox.execute(manifest, "test_tool", medium_handler, {})
        assert result.success is False
        assert "timed out" in result.error.lower()

    async def test_concurrency_limit(self) -> None:
        """Exceeding max concurrent executions returns an error."""
        sandbox = PluginSandbox(SandboxConfig(max_concurrent_executions=1))
        manifest = _make_manifest(timeout=5.0)

        # Simulate active execution
        sandbox._active_executions = 1

        async def handler() -> ToolResult:
            return ToolResult(success=True, output="ok")

        result = await sandbox.execute(manifest, "test_tool", handler, {})
        assert result.success is False
        assert "concurrent" in result.error.lower()


class TestRestrictedImporter:
    """Test the RestrictedImporter context manager."""

    def test_blocked_import_raises(self) -> None:
        """Importing a blocked module raises ImportError."""
        with RestrictedImporter(blocked={"os"}):
            with pytest.raises(ImportError, match="blocked by the plugin sandbox"):
                __import__("os")

    def test_allowed_import_succeeds(self) -> None:
        """Non-blocked modules can still be imported."""
        with RestrictedImporter(blocked={"os"}):
            # json is not blocked, should work fine
            import json

            assert json is not None

    def test_whitelist_overrides_blocked(self) -> None:
        """Whitelisted modules are allowed even if in blocked set."""
        with RestrictedImporter(blocked={"os"}, whitelist={"os"}):
            import os

            assert os is not None

    def test_submodule_blocked_by_parent(self) -> None:
        """Blocking 'os' also blocks 'os.path'."""
        with RestrictedImporter(blocked={"os"}):
            with pytest.raises(ImportError, match="blocked"):
                __import__("os.path")

    def test_original_import_restored_after_exit(self) -> None:
        """After exiting the context, imports work normally again."""
        import builtins

        original = builtins.__import__

        with RestrictedImporter(blocked={"os"}):
            pass  # Exit context

        # Import should work normally now
        assert builtins.__import__ is original
        import os

        assert os is not None

    def test_default_blocked_imports_include_dangerous_modules(self) -> None:
        """Default blocked set includes os, subprocess, sys."""
        assert "os" in DEFAULT_BLOCKED_IMPORTS
        assert "subprocess" in DEFAULT_BLOCKED_IMPORTS
        assert "sys" in DEFAULT_BLOCKED_IMPORTS
        assert "ctypes" in DEFAULT_BLOCKED_IMPORTS

    def test_multiple_blocked_modules(self) -> None:
        """Multiple modules can be blocked simultaneously."""
        with RestrictedImporter(blocked={"os", "subprocess", "sys"}):
            with pytest.raises(ImportError):
                __import__("os")
            with pytest.raises(ImportError):
                __import__("subprocess")
            with pytest.raises(ImportError):
                __import__("sys")


class TestSandboxImportRestrictions:
    """Test import restrictions within full sandbox execution."""

    async def test_plugin_cannot_import_os_by_default(self) -> None:
        """Plugin without shell permission cannot import os."""
        sandbox = PluginSandbox()
        manifest = _make_manifest(permissions=[])

        async def handler_importing_os() -> ToolResult:
            try:
                __import__("os")
                return ToolResult(success=True, output="imported os")
            except ImportError as e:
                return ToolResult(success=False, error=str(e))

        result = await sandbox.execute(manifest, "test_tool", handler_importing_os, {})
        # The handler catches the ImportError itself
        assert result.success is False
        assert "blocked" in result.error.lower()

    async def test_plugin_with_shell_permission_can_import_os(self) -> None:
        """Plugin with shell:exec permission can import os."""
        sandbox = PluginSandbox()
        manifest = _make_manifest(permissions=[PluginPermission.SHELL_EXEC])

        async def handler_importing_os() -> ToolResult:
            import os

            return ToolResult(success=True, output=f"cwd={os.getcwd()}")

        result = await sandbox.execute(manifest, "test_tool", handler_importing_os, {})
        assert result.success is True
        assert "cwd=" in result.output

    async def test_plugin_with_network_permission_can_import_socket(self) -> None:
        """Plugin with network permission can import socket."""
        sandbox = PluginSandbox()
        manifest = _make_manifest(permissions=[PluginPermission.NETWORK_LOCAL])

        async def handler_importing_socket() -> ToolResult:
            import socket

            return ToolResult(success=True, output=f"socket={socket.__name__}")

        result = await sandbox.execute(manifest, "test_tool", handler_importing_socket, {})
        assert result.success is True
        assert "socket" in result.output


class TestSandboxFileAccess:
    """Test file access permission checks."""

    def test_blocked_path_raises_violation(self) -> None:
        """Accessing a blocked path raises SandboxViolation."""
        sandbox = PluginSandbox()
        ctx = ExecutionContext(
            plugin_name="test-plugin",
            tool_name="test",
            permissions={PluginPermission.FILESYSTEM_READ},
            timeout_seconds=30.0,
            max_memory_mb=256,
        )

        with pytest.raises(SandboxViolation, match="blocked path"):
            sandbox.check_file_access(ctx, "/etc/shadow", write=False)

    def test_write_without_permission_raises_violation(self) -> None:
        """Writing without FILESYSTEM_WRITE permission raises violation."""
        sandbox = PluginSandbox()
        ctx = ExecutionContext(
            plugin_name="test-plugin",
            tool_name="test",
            permissions={PluginPermission.FILESYSTEM_READ},
            timeout_seconds=30.0,
            max_memory_mb=256,
        )

        with pytest.raises(SandboxViolation, match="Write access"):
            sandbox.check_file_access(ctx, "/tmp/mk/test.txt", write=True)

    def test_read_without_permission_raises_violation(self) -> None:
        """Reading without FILESYSTEM_READ permission raises violation."""
        sandbox = PluginSandbox()
        ctx = ExecutionContext(
            plugin_name="test-plugin",
            tool_name="test",
            permissions=set(),
            timeout_seconds=30.0,
            max_memory_mb=256,
        )

        with pytest.raises(SandboxViolation, match="Read access"):
            sandbox.check_file_access(ctx, "/data/test.txt", write=False)


class TestSandboxViolationException:
    """Test the SandboxViolation exception class."""

    def test_violation_attributes(self) -> None:
        """SandboxViolation stores plugin name and violation details."""
        violation = SandboxViolation(
            plugin="my-plugin",
            violation="tried to read /etc/shadow",
            permission="filesystem:read",
        )
        assert violation.plugin == "my-plugin"
        assert violation.violation == "tried to read /etc/shadow"
        assert violation.permission == "filesystem:read"
        assert "my-plugin" in str(violation)

    def test_violation_string_representation(self) -> None:
        """SandboxViolation has informative string repr."""
        violation = SandboxViolation(
            plugin="bad-plugin",
            violation="timeout exceeded",
        )
        msg = str(violation)
        assert "bad-plugin" in msg
        assert "timeout exceeded" in msg
