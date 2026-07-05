"""MK Configuration management.

Provides configuration loading and validation via Pydantic models.
Configuration is loaded from YAML files and validated at startup.
"""

from mk.config.settings import Settings, load_config

__all__ = ["Settings", "load_config"]
