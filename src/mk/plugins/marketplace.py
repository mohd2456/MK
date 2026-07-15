"""Plugin marketplace — install, list, and search MK plugins.

Plugins are YAML-declared tool packs with optional Python handlers.
They live in a plugins directory (default: /opt/mk/plugins or ~/.mk/plugins).
This module provides a CLI and programmatic interface to:
- List installed plugins
- Install from a git URL or local path
- Search a registry (future: community index)
- Remove plugins

Usage:
    mk-plugin list
    mk-plugin install https://github.com/user/mk-plugin-foo.git
    mk-plugin install /path/to/local/plugin
    mk-plugin remove plugin-name
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_PLUGIN_DIR = os.environ.get("MK_PLUGIN_DIR", str(Path.home() / ".mk" / "plugins"))


def get_plugin_dir() -> Path:
    """Return the configured plugin directory, creating it if needed."""
    d = Path(DEFAULT_PLUGIN_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_plugins(plugin_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all installed plugins with their metadata.

    Returns:
        List of plugin info dicts (name, version, description, tools, path).
    """
    d = Path(plugin_dir) if plugin_dir else get_plugin_dir()
    plugins: List[Dict[str, Any]] = []
    if not d.exists():
        return plugins

    for entry in sorted(d.iterdir()):
        manifest = entry / "plugin.yaml"
        if not manifest.exists():
            manifest = entry / "plugin.yml"
        if not manifest.exists():
            continue
        try:
            data = yaml.safe_load(manifest.read_text())
            plugins.append(
                {
                    "name": data.get("name", entry.name),
                    "version": data.get("version", "0.0.0"),
                    "description": data.get("description", ""),
                    "tools": [t.get("name", "") for t in data.get("tools", [])],
                    "path": str(entry),
                }
            )
        except Exception as exc:
            logger.warning("Failed to read plugin %s: %s", entry.name, exc)
    return plugins


def install_plugin(source: str, plugin_dir: Optional[str] = None) -> Dict[str, Any]:
    """Install a plugin from a git URL or local path.

    Args:
        source: Git URL (.git suffix) or local directory path.
        plugin_dir: Override plugin directory.

    Returns:
        Info dict of the installed plugin.

    Raises:
        ValueError: If the source is invalid or install fails.
    """
    d = Path(plugin_dir) if plugin_dir else get_plugin_dir()
    source_path = Path(source)

    if source.endswith(".git") or source.startswith("https://") or source.startswith("git@"):
        # Git clone
        # Derive plugin name from URL
        name = source.rstrip("/").split("/")[-1].replace(".git", "")
        target = d / name
        if target.exists():
            raise ValueError(f"Plugin '{name}' already installed at {target}")
        result = subprocess.run(
            ["git", "clone", "--depth=1", source, str(target)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise ValueError(f"Git clone failed: {result.stderr[:200]}")
    elif source_path.is_dir():
        # Local copy
        name = source_path.name
        target = d / name
        if target.exists():
            raise ValueError(f"Plugin '{name}' already installed at {target}")
        shutil.copytree(source_path, target)
    else:
        raise ValueError(f"Invalid source: {source} (expected git URL or directory)")

    # Verify it has a plugin.yaml
    manifest = target / "plugin.yaml"
    if not manifest.exists():
        manifest = target / "plugin.yml"
    if not manifest.exists():
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError(f"No plugin.yaml found in {source}")

    data = yaml.safe_load(manifest.read_text())
    return {
        "name": data.get("name", name),
        "version": data.get("version", "0.0.0"),
        "description": data.get("description", ""),
        "tools": [t.get("name", "") for t in data.get("tools", [])],
        "path": str(target),
    }


def remove_plugin(name: str, plugin_dir: Optional[str] = None) -> bool:
    """Remove an installed plugin by name.

    Returns:
        True if removed, False if not found.
    """
    d = Path(plugin_dir) if plugin_dir else get_plugin_dir()
    target = d / name
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
        return True
    return False


def search_plugins(query: str) -> List[Dict[str, str]]:
    """Search the plugin registry (placeholder for community index).

    Currently returns the built-in example plugins that match the query.
    In the future, this will query a remote index.
    """
    # Placeholder: search the examples/plugins directory
    examples_dir = Path(__file__).parent.parent.parent.parent / "examples" / "plugins"
    results: List[Dict[str, str]] = []
    if examples_dir.exists():
        for entry in examples_dir.iterdir():
            manifest = entry / "plugin.yaml"
            if not manifest.exists():
                continue
            try:
                data = yaml.safe_load(manifest.read_text())
                name = data.get("name", entry.name)
                desc = data.get("description", "")
                if query.lower() in name.lower() or query.lower() in desc.lower():
                    results.append({"name": name, "description": desc, "source": str(entry)})
            except Exception:
                continue
    return results


# ─── CLI Entry Point ──────────────────────────────────────────────────────────


def cli_entry() -> None:
    """CLI entry point for 'mk-plugin'."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="mk-plugin",
        description="MK Plugin Manager — install, list, and search plugins",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="List installed plugins")

    # install
    install_p = sub.add_parser("install", help="Install a plugin from URL or path")
    install_p.add_argument("source", help="Git URL or local directory path")

    # remove
    remove_p = sub.add_parser("remove", help="Remove an installed plugin")
    remove_p.add_argument("name", help="Plugin name to remove")

    # search
    search_p = sub.add_parser("search", help="Search available plugins")
    search_p.add_argument("query", help="Search query")

    args = parser.parse_args()

    if args.command == "list":
        plugins = list_plugins()
        if not plugins:
            print("No plugins installed.")
            print(f"Plugin directory: {get_plugin_dir()}")
            print("\nInstall one: mk-plugin install https://github.com/user/plugin.git")
            return
        print(f"Installed plugins ({len(plugins)}):\n")
        for p in plugins:
            print(f"  {p['name']} v{p['version']}")
            if p["description"]:
                print(f"    {p['description']}")
            if p["tools"]:
                print(f"    Tools: {', '.join(p['tools'])}")
            print()

    elif args.command == "install":
        try:
            info = install_plugin(args.source)
            print(f"✓ Installed: {info['name']} v{info['version']}")
            if info["tools"]:
                print(f"  Tools: {', '.join(info['tools'])}")
            print(f"  Path: {info['path']}")
        except ValueError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "remove":
        if remove_plugin(args.name):
            print(f"✓ Removed: {args.name}")
        else:
            print(f"✗ Plugin '{args.name}' not found", file=sys.stderr)
            sys.exit(1)

    elif args.command == "search":
        results = search_plugins(args.query)
        if not results:
            print(f"No plugins found for '{args.query}'")
            return
        print(f"Found {len(results)} plugin(s):\n")
        for r in results:
            print(f"  {r['name']}: {r['description']}")
            print(f"    Install: mk-plugin install {r['source']}")
            print()

    else:
        parser.print_help()


if __name__ == "__main__":
    cli_entry()
