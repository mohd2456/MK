"""Plugin loader — discovers, validates, and loads plugins from disk.

Scans configured directories for plugin folders containing a
plugin.yaml manifest and a tools.py (or tools/ package) with
the actual implementation.

Directory structure expected:
    ~/.mk/plugins/
    ├── plex-manager/
    │   ├── plugin.yaml       # Manifest (required)
    │   └── tools.py          # Tool implementations (required)
    ├── dns-updater/
    │   ├── plugin.yaml
    │   ├── tools.py
    │   └── templates/        # Optional extra files
    │       └── zone.j2
    └── backup-verifier/
        ├── plugin.yaml
        └── tools/            # Can also be a package
            ├── __init__.py
            └── verify.py
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from mk.plugins.manifest import PluginManifest
from mk.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class LoadedPlugin:
    """A fully loaded and ready-to-execute plugin.

    Contains the parsed manifest, the loaded Python module,
    and a mapping of tool names to their handler functions.
    """

    manifest: PluginManifest
    path: Path
    module: Any
    handlers: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    loaded_at: float = field(default_factory=time.time)
    load_errors: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Plugin name from manifest."""
        return self.manifest.name

    @property
    def tool_names(self) -> List[str]:
        """Names of all tools this plugin provides."""
        return list(self.handlers.keys())

    @property
    def is_healthy(self) -> bool:
        """Whether the plugin loaded without errors."""
        return len(self.load_errors) == 0

    def get_handler(self, tool_name: str) -> Optional[Callable[..., Any]]:
        """Get the handler function for a tool.

        Args:
            tool_name: The tool name to look up.

        Returns:
            The async handler function, or None if not found.
        """
        return self.handlers.get(tool_name)


class PluginLoader:
    """Discovers and loads plugins from the filesystem.

    Scans directories for valid plugin folders (containing
    plugin.yaml + tools.py), validates them, loads the Python
    modules, and extracts tool handler functions.

    Tool handlers are identified by:
    1. Functions decorated with @tool (if using the decorator pattern)
    2. Async functions whose names match tool names in the manifest
    3. Classes that subclass mk.tools.base.Tool (legacy compatibility)
    """

    def __init__(self, plugin_dirs: Optional[List[str]] = None) -> None:
        """Initialize the plugin loader.

        Args:
            plugin_dirs: List of directories to scan for plugins.
                Defaults to [~/.mk/plugins/].
        """
        if plugin_dirs:
            self._plugin_dirs = [Path(d) for d in plugin_dirs]
        else:
            self._plugin_dirs = [Path.home() / ".mk" / "plugins"]

    @property
    def plugin_dirs(self) -> List[Path]:
        """Configured plugin directories."""
        return list(self._plugin_dirs)

    def discover(self) -> List[Path]:
        """Discover all plugin directories.

        Scans each configured plugin directory for subdirectories
        that contain a plugin.yaml file.

        Returns:
            List of paths to discovered plugin directories.
        """
        discovered: List[Path] = []

        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                logger.debug(f"Plugin directory does not exist: {plugin_dir}")
                continue

            if not plugin_dir.is_dir():
                logger.warning(f"Plugin path is not a directory: {plugin_dir}")
                continue

            for entry in sorted(plugin_dir.iterdir()):
                if not entry.is_dir():
                    continue

                manifest_path = entry / "plugin.yaml"
                if manifest_path.exists():
                    discovered.append(entry)
                else:
                    # Also check plugin.yml
                    manifest_path_alt = entry / "plugin.yml"
                    if manifest_path_alt.exists():
                        discovered.append(entry)

        logger.info(f"Discovered {len(discovered)} plugins across {len(self._plugin_dirs)} directories")
        return discovered

    def load_plugin(self, plugin_path: Path) -> LoadedPlugin:
        """Load a single plugin from its directory.

        Steps:
        1. Parse and validate the manifest
        2. Load the Python module (tools.py or tools/)
        3. Extract handler functions for each declared tool
        4. Return a LoadedPlugin (even if there were non-fatal errors)

        Args:
            plugin_path: Path to the plugin directory.

        Returns:
            LoadedPlugin instance (check .is_healthy for errors).

        Raises:
            FileNotFoundError: If no manifest is found.
            ValueError: If the manifest is fundamentally broken.
        """
        # Find and parse manifest
        manifest = self._load_manifest(plugin_path)

        # Load the Python module
        module, module_errors = self._load_module(plugin_path, manifest.name)

        # Extract handlers
        handlers: Dict[str, Callable[..., Any]] = {}
        extraction_errors: List[str] = []

        if module:
            handlers, extraction_errors = self._extract_handlers(
                module, manifest
            )

        all_errors = module_errors + extraction_errors

        loaded = LoadedPlugin(
            manifest=manifest,
            path=plugin_path,
            module=module,
            handlers=handlers,
            load_errors=all_errors,
        )

        if all_errors:
            logger.warning(
                f"Plugin '{manifest.name}' loaded with {len(all_errors)} errors: "
                f"{all_errors}"
            )
        else:
            logger.info(
                f"Plugin '{manifest.name}' loaded: "
                f"{len(handlers)} tools ({', '.join(handlers.keys())})"
            )

        return loaded

    def load_all(self) -> List[LoadedPlugin]:
        """Discover and load all available plugins.

        Returns:
            List of all loaded plugins (including those with errors).
        """
        discovered = self.discover()
        plugins: List[LoadedPlugin] = []

        for plugin_path in discovered:
            try:
                plugin = self.load_plugin(plugin_path)
                plugins.append(plugin)
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Failed to load plugin at {plugin_path}: {e}")
            except Exception as e:
                logger.error(
                    f"Unexpected error loading plugin at {plugin_path}: {e}",
                    exc_info=True,
                )

        return plugins

    def reload_plugin(self, plugin: LoadedPlugin) -> LoadedPlugin:
        """Reload a plugin from disk (hot-reload).

        Removes the old module from sys.modules and re-imports it.
        This allows plugins to be updated without restarting MK.

        Args:
            plugin: The currently loaded plugin to reload.

        Returns:
            Freshly loaded plugin instance.
        """
        # Remove old module from sys.modules
        module_name = f"mk_plugin_{plugin.name.replace('-', '_')}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        logger.info(f"Reloading plugin '{plugin.name}' from {plugin.path}")
        return self.load_plugin(plugin.path)

    def _load_manifest(self, plugin_path: Path) -> PluginManifest:
        """Load and validate the plugin manifest.

        Args:
            plugin_path: Plugin directory path.

        Returns:
            Validated PluginManifest.

        Raises:
            FileNotFoundError: If no manifest file exists.
            ValueError: If manifest is invalid.
        """
        # Try plugin.yaml first, then plugin.yml
        for filename in ("plugin.yaml", "plugin.yml"):
            manifest_path = plugin_path / filename
            if manifest_path.exists():
                return PluginManifest.from_yaml(manifest_path)

        raise FileNotFoundError(
            f"No plugin.yaml or plugin.yml found in {plugin_path}"
        )

    def _load_module(
        self, plugin_path: Path, plugin_name: str
    ) -> tuple:
        """Load the plugin's Python module.

        Looks for tools.py or tools/__init__.py in the plugin directory.

        Args:
            plugin_path: Plugin directory path.
            plugin_name: Plugin name (used for module naming).

        Returns:
            Tuple of (module, list_of_errors).
        """
        errors: List[str] = []

        # Find the tools module
        tools_file = plugin_path / "tools.py"
        tools_package = plugin_path / "tools" / "__init__.py"

        if tools_file.exists():
            module_path = tools_file
        elif tools_package.exists():
            module_path = tools_package
        else:
            errors.append("No tools.py or tools/ package found")
            return None, errors

        # Load the module dynamically
        module_name = f"mk_plugin_{plugin_name.replace('-', '_')}"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, str(module_path)
            )
            if spec is None or spec.loader is None:
                errors.append(f"Failed to create module spec from {module_path}")
                return None, errors

            module = importlib.util.module_from_spec(spec)

            # Temporarily add plugin path so relative imports within the plugin work
            path_added = False
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))
                path_added = True

            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                # Clean up sys.path to prevent pollution across plugins
                if path_added:
                    try:
                        sys.path.remove(str(plugin_path))
                    except ValueError:
                        pass

            return module, errors
        except Exception as e:
            errors.append(f"Module import failed: {type(e).__name__}: {e}")
            return None, errors

    def _extract_handlers(
        self, module: Any, manifest: PluginManifest
    ) -> tuple:
        """Extract tool handler functions from the loaded module.

        Matching strategy:
        1. Look for functions named exactly as the tool (e.g., def search_movie)
        2. Look for functions with a _tool suffix (e.g., def search_movie_tool)
        3. Look for Tool subclasses whose .name matches
        4. Look for a 'tools' dict in the module (explicit registration)

        Args:
            module: The loaded Python module.
            manifest: Plugin manifest (declares expected tools).

        Returns:
            Tuple of (handlers_dict, errors_list).
        """
        handlers: Dict[str, Callable[..., Any]] = {}
        errors: List[str] = []

        # Strategy 1: Check for an explicit `tools` dict in the module
        if hasattr(module, "tools") and isinstance(module.tools, dict):
            for tool_name, handler in module.tools.items():
                if tool_name in manifest.tool_names:
                    if callable(handler):
                        handlers[tool_name] = handler
                    else:
                        errors.append(
                            f"Tool '{tool_name}' in module.tools is not callable"
                        )

        # Strategy 2: Look for functions matching tool names
        for tool_def in manifest.tools:
            if tool_def.name in handlers:
                continue  # Already found via explicit dict

            # Try exact name match
            func = getattr(module, tool_def.name, None)
            if func and callable(func):
                handlers[tool_def.name] = func
                continue

            # Try with _tool suffix
            func = getattr(module, f"{tool_def.name}_tool", None)
            if func and callable(func):
                handlers[tool_def.name] = func
                continue

            # Try with handle_ prefix
            func = getattr(module, f"handle_{tool_def.name}", None)
            if func and callable(func):
                handlers[tool_def.name] = func
                continue

        # Strategy 3: Look for Tool subclasses (legacy compatibility)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Tool)
                and obj is not Tool
                and not inspect.isabstract(obj)
            ):
                try:
                    instance = obj()
                    if instance.name in manifest.tool_names and instance.name not in handlers:
                        # Wrap the Tool.execute() as a handler
                        handlers[instance.name] = instance.execute
                except Exception:
                    pass  # Tool requires args, skip

        # Report missing handlers
        for tool_def in manifest.tools:
            if tool_def.name not in handlers:
                errors.append(
                    f"No handler found for declared tool '{tool_def.name}'"
                )

        return handlers, errors
