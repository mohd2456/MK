"""MK Plugin System.

Drop-in plugin architecture for extending MK with new tools.
Plugins are discovered from configurable directories, validated
against their manifests, and executed in isolated sandboxes.

Architecture:
    - PluginManifest: Declares what a plugin is and what it can do
    - PluginLoader: Discovers and loads plugins from disk
    - PluginSandbox: Isolates plugin execution with resource limits
    - PluginManager: Orchestrates the full lifecycle (load, reload, unload)

Usage:
    manager = PluginManager(plugin_dirs=["/path/to/plugins"])
    await manager.load_all()
    result = await manager.execute("my_plugin", "my_tool", args={...})
"""

from mk.plugins.manifest import PluginManifest, PluginPermission, PluginTool
from mk.plugins.loader import PluginLoader, LoadedPlugin
from mk.plugins.sandbox import PluginSandbox, SandboxConfig, SandboxViolation
from mk.plugins.manager import PluginManager

__all__ = [
    "PluginManifest",
    "PluginPermission",
    "PluginTool",
    "PluginLoader",
    "LoadedPlugin",
    "PluginSandbox",
    "SandboxConfig",
    "SandboxViolation",
    "PluginManager",
]
