"""Plugin manifest models.

A plugin manifest (plugin.yaml) declares everything about a plugin:
- Identity (name, version, author, description)
- Tools it provides (name, description, parameters schema)
- Permissions it requires (filesystem, network, shell, docker)
- Dependencies (other plugins or Python packages)
- Triggers (events that auto-invoke the plugin)

The manifest is the contract between the plugin and MK.
MK will never grant a plugin more access than its manifest declares.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class PluginPermission(str, Enum):
    """Permissions a plugin can request.

    Each permission grants access to a specific capability.
    Plugins only get what they explicitly declare.
    """

    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    NETWORK_LOCAL = "network:local"
    NETWORK_INTERNET = "network:internet"
    SHELL_EXEC = "shell:exec"
    DOCKER_READ = "docker:read"
    DOCKER_WRITE = "docker:write"
    SSH_CONNECT = "ssh:connect"
    SECRETS_READ = "secrets:read"
    SYSTEM_INFO = "system:info"
    PROACTIVE_SEND = "proactive:send"


class PluginTool(BaseModel):
    """A single tool provided by a plugin.

    Each plugin can expose multiple tools. Each tool has its own
    name, description, and parameter schema — these are what the
    LLM sees when deciding which tool to call.
    """

    name: str = Field(description="Tool name (must be unique within the plugin)")
    description: str = Field(description="Human-readable description for LLM prompts")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema defining accepted parameters",
    )
    dangerous: bool = Field(
        default=False,
        description="Whether this tool performs destructive/irreversible actions",
    )
    confirm_message: Optional[str] = Field(
        default=None,
        description="Custom confirmation prompt if dangerous=true",
    )


class PluginTrigger(BaseModel):
    """An event that can automatically invoke a plugin tool.

    Triggers let plugins react to system events without being
    explicitly called by the user or LLM.
    """

    event: str = Field(description="Event name (e.g., 'container:unhealthy', 'schedule:daily')")
    tool: str = Field(description="Which tool in this plugin to invoke")
    args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default arguments to pass to the tool",
    )
    condition: Optional[str] = Field(
        default=None,
        description="Optional condition expression (e.g., 'event.count > 2')",
    )


class PluginManifest(BaseModel):
    """Complete plugin manifest — the plugin.yaml contract.

    This is the single source of truth for what a plugin is,
    what it does, and what it needs. MK reads this to understand
    how to load, sandbox, and expose the plugin.
    """

    # Identity
    name: str = Field(description="Plugin name (unique identifier, kebab-case)")
    version: str = Field(default="0.1.0", description="Semantic version")
    description: str = Field(description="What this plugin does (shown in help)")
    author: Optional[str] = Field(default=None, description="Plugin author")

    # What it provides
    tools: List[PluginTool] = Field(
        default_factory=list,
        description="Tools this plugin exposes to MK",
    )

    # What it needs
    permissions: List[PluginPermission] = Field(
        default_factory=list,
        description="Permissions this plugin requires",
    )
    python_deps: List[str] = Field(
        default_factory=list,
        description="Python package dependencies (pip format)",
    )
    plugin_deps: List[str] = Field(
        default_factory=list,
        description="Other plugins this depends on (by name)",
    )

    # Automation
    triggers: List[PluginTrigger] = Field(
        default_factory=list,
        description="Events that auto-invoke this plugin",
    )

    # Runtime config
    timeout_seconds: float = Field(
        default=30.0,
        description="Maximum execution time per tool call",
    )
    max_memory_mb: int = Field(
        default=256,
        description="Maximum memory usage in MB",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this plugin is active",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure plugin name is kebab-case and reasonable."""
        import re

        if not re.match(r"^[a-z][a-z0-9\-]*$", v):
            raise ValueError(
                f"Plugin name must be kebab-case (lowercase, hyphens): got '{v}'"
            )
        if len(v) > 64:
            raise ValueError("Plugin name must be 64 characters or less")
        return v

    @property
    def tool_names(self) -> List[str]:
        """Get all tool names provided by this plugin."""
        return [t.name for t in self.tools]

    @property
    def qualified_tool_names(self) -> List[str]:
        """Get fully-qualified tool names (plugin_name.tool_name)."""
        return [f"{self.name}.{t.name}" for t in self.tools]

    def get_tool(self, name: str) -> Optional[PluginTool]:
        """Look up a tool by name.

        Args:
            name: Tool name (unqualified).

        Returns:
            PluginTool if found, None otherwise.
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def has_permission(self, permission: PluginPermission) -> bool:
        """Check if this plugin declares a specific permission.

        Args:
            permission: The permission to check.

        Returns:
            True if the plugin declares this permission.
        """
        return permission in self.permissions

    @classmethod
    def from_yaml(cls, path: Path) -> "PluginManifest":
        """Load a manifest from a plugin.yaml file.

        Args:
            path: Path to the plugin.yaml file.

        Returns:
            Validated PluginManifest instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the manifest is invalid.
        """
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            raise ValueError(f"Invalid manifest (empty or not a dict): {path}")

        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """Write the manifest to a YAML file.

        Args:
            path: Destination path for the manifest.
        """
        data = self.model_dump(mode="json", exclude_none=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
