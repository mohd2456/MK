"""Configuration system for MK.

Loads configuration from YAML files and validates using Pydantic models.
Supports LLM providers, machines, services, memory settings, safety settings,
and Telegram integration configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    name: str = Field(description="Provider name (e.g., 'claude', 'openai', 'groq')")
    api_key_ref: str = Field(description="Reference to the API key in secrets store")
    model: str = Field(description="Model identifier (e.g., 'claude-3-sonnet')")
    endpoint: str = Field(description="API endpoint URL")
    priority: int = Field(default=0, description="Priority (higher = preferred)")
    max_tokens: int = Field(default=4096, description="Maximum tokens per response")
    temperature: float = Field(default=0.7, description="Sampling temperature")


class MachineConfig(BaseModel):
    """Configuration for a remote machine in the homelab."""

    name: str = Field(description="Machine identifier")
    host: str = Field(description="Hostname or IP address")
    user: str = Field(default="root", description="SSH user")
    ssh_key_path: Optional[str] = Field(default=None, description="Path to SSH key")
    roles: List[str] = Field(default_factory=list, description="Machine roles (e.g., 'media')")


class ServiceConfig(BaseModel):
    """Configuration for a managed service."""

    name: str = Field(description="Service name")
    url: str = Field(description="Service URL")
    api_key_ref: Optional[str] = Field(default=None, description="API key reference")
    machine: Optional[str] = Field(default=None, description="Machine the service runs on")


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    short_term_max_messages: int = Field(
        default=50, description="Max messages in short-term memory"
    )
    long_term_storage_path: str = Field(
        default="~/.mk/memory", description="Path for long-term memory storage"
    )
    context_window_budget: int = Field(
        default=8000, description="Token budget for context window"
    )
    summary_threshold: int = Field(
        default=20, description="Messages before triggering summarization"
    )


class SafetyConfig(BaseModel):
    """Safety and confirmation settings."""

    confirm_destructive: bool = Field(
        default=True, description="Require confirmation for destructive actions"
    )
    audit_log_path: str = Field(
        default="~/.mk/audit.log", description="Path for audit log"
    )
    max_iterations: int = Field(
        default=10, description="Maximum agent loop iterations"
    )
    secrets_path: str = Field(
        default="~/.mk/secrets.enc", description="Path to encrypted secrets file"
    )


class TelegramConfig(BaseModel):
    """Telegram messaging integration configuration."""

    enabled: bool = Field(default=False, description="Whether Telegram is enabled")
    bot_token_ref: Optional[str] = Field(default=None, description="Bot token reference")
    allowed_chat_ids: List[int] = Field(
        default_factory=list, description="Allowed Telegram chat IDs"
    )


class TailscaleConfig(BaseModel):
    """Tailscale mesh VPN configuration."""

    enabled: bool = Field(default=False, description="Whether Tailscale is enabled")
    auth_key_ref: Optional[str] = Field(
        default=None, description="Auth key reference in secrets store"
    )
    hostname: Optional[str] = Field(
        default=None, description="Hostname on the tailnet (e.g., 'mk-brain')"
    )
    advertise_routes: List[str] = Field(
        default_factory=list,
        description="Subnets to advertise (e.g., ['192.168.1.0/24'])",
    )
    advertise_exit_node: bool = Field(
        default=False, description="Offer this node as an exit node"
    )
    accept_routes: bool = Field(
        default=True, description="Accept routes from other tailnet nodes"
    )
    ssh: bool = Field(
        default=True, description="Enable Tailscale SSH"
    )
    serve: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Services to expose on tailnet [{port, path}]",
    )
    funnel: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Services to expose publicly [{port, path}]",
    )


class Settings(BaseModel):
    """Root configuration model for MK.

    Validates all configuration sections and provides typed access
    to all settings needed by the MK engine.
    """

    llm_providers: List[LLMProviderConfig] = Field(
        default_factory=list, description="Configured LLM providers"
    )
    machines: List[MachineConfig] = Field(
        default_factory=list, description="Managed machines"
    )
    services: List[ServiceConfig] = Field(
        default_factory=list, description="Managed services"
    )
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="Memory settings")
    safety: SafetyConfig = Field(default_factory=SafetyConfig, description="Safety settings")
    telegram: TelegramConfig = Field(
        default_factory=TelegramConfig, description="Telegram settings"
    )
    tailscale: TailscaleConfig = Field(
        default_factory=TailscaleConfig, description="Tailscale VPN settings"
    )

    @property
    def active_providers(self) -> List[LLMProviderConfig]:
        """Return providers sorted by priority (highest first)."""
        return sorted(self.llm_providers, key=lambda p: p.priority, reverse=True)


def load_config(config_path: Optional[str] = None) -> Settings:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to the YAML config file. If None, looks for
            config.yaml in ~/.mk/ and current directory.

    Returns:
        Validated Settings instance.

    Raises:
        FileNotFoundError: If no config file is found.
        ValueError: If the config file is invalid.
    """
    search_paths: List[Path] = []

    if config_path:
        search_paths.append(Path(config_path))
    else:
        search_paths.extend([
            Path.home() / ".mk" / "config.yaml",
            Path("config.yaml"),
        ])

    config_data: Dict[str, Any] = {}

    for path in search_paths:
        if path.exists():
            with open(path, "r") as f:
                loaded = yaml.safe_load(f)
                if loaded and isinstance(loaded, dict):
                    config_data = loaded
            break

    return Settings(**config_data)
