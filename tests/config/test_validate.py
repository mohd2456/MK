"""Tests for config validation.

Tests valid config, missing provider, and invalid field scenarios.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mk.config.validate import ValidationResult, validate_config


@pytest.fixture
def valid_config(tmp_path: Path) -> str:
    """Create a valid config.yaml file and return its path."""
    config = {
        "llm_providers": [
            {
                "name": "openai",
                "api_key_ref": "openai_key",
                "model": "gpt-4o",
                "endpoint": "https://api.openai.com/v1",
                "priority": 1,
                "max_tokens": 4096,
                "temperature": 0.7,
            }
        ],
        "machines": [
            {
                "name": "nas",
                "host": "192.168.1.10",
                "user": "root",
                "roles": ["storage"],
            }
        ],
        "memory": {
            "short_term_max_messages": 50,
            "long_term_storage_path": "~/.mk/memory",
            "context_window_budget": 8000,
            "summary_threshold": 20,
        },
        "safety": {
            "confirm_destructive": True,
            "audit_log_path": "~/.mk/audit.log",
            "max_iterations": 10,
            "secrets_path": "~/.mk/secrets.enc",
        },
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path)


@pytest.fixture
def minimal_config(tmp_path: Path) -> str:
    """Create a minimal valid config (empty but parseable)."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump({}, f)
    return str(config_path)


class TestValidConfig:
    """Test validation of a correct config file."""

    def test_valid_config_passes(self, valid_config: str) -> None:
        """A well-formed config passes validation."""
        result = validate_config(valid_config)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_config_has_path(self, valid_config: str) -> None:
        """Result includes the config file path."""
        result = validate_config(valid_config)
        assert result.config_path == valid_config

    def test_minimal_config_is_valid(self, minimal_config: str) -> None:
        """A minimal config (no providers) is valid but produces warnings."""
        result = validate_config(minimal_config)
        # Valid because no hard errors, just missing providers warning
        assert result.valid is True


class TestMissingProvider:
    """Test validation when LLM providers are missing or invalid."""

    def test_no_providers_produces_warning(self, minimal_config: str) -> None:
        """Empty llm_providers list triggers a warning."""
        result = validate_config(minimal_config)
        warnings = result.warnings
        assert any("LLM providers" in w.message for w in warnings)

    def test_provider_without_endpoint(self, tmp_path: Path) -> None:
        """Provider without an endpoint produces an error."""
        config = {
            "llm_providers": [
                {
                    "name": "test",
                    "api_key_ref": "key_ref",
                    "model": "model",
                    "endpoint": "",
                    "priority": 0,
                }
            ],
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = validate_config(str(config_path))
        assert result.valid is False
        assert any("endpoint" in e.field for e in result.errors)

    def test_provider_without_api_key_ref_is_warning(self, tmp_path: Path) -> None:
        """Provider without api_key_ref produces a warning, not error."""
        config = {
            "llm_providers": [
                {
                    "name": "local",
                    "api_key_ref": "",
                    "model": "llama",
                    "endpoint": "http://localhost:11434",
                    "priority": 0,
                }
            ],
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = validate_config(str(config_path))
        warnings = result.warnings
        assert any("API key" in w.message for w in warnings)


class TestInvalidFields:
    """Test validation with invalid field values."""

    def test_machine_without_host(self, tmp_path: Path) -> None:
        """Machine without a host field produces an error."""
        config = {
            "machines": [
                {
                    "name": "broken-machine",
                    "host": "",
                    "user": "root",
                }
            ],
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = validate_config(str(config_path))
        assert result.valid is False
        assert any("host" in e.field for e in result.errors)

    def test_safety_max_iterations_zero(self, tmp_path: Path) -> None:
        """max_iterations < 1 produces an error."""
        config = {
            "safety": {
                "max_iterations": 0,
            },
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = validate_config(str(config_path))
        assert result.valid is False
        assert any("max_iterations" in e.field for e in result.errors)

    def test_safety_max_iterations_too_high_is_warning(self, tmp_path: Path) -> None:
        """max_iterations > 50 produces a warning."""
        config = {
            "safety": {
                "max_iterations": 100,
            },
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        result = validate_config(str(config_path))
        # Still valid, just warned
        assert result.valid is True
        assert any("max_iterations" in w.field for w in result.warnings)

    def test_invalid_yaml_file(self, tmp_path: Path) -> None:
        """Invalid YAML produces an error."""
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: [: content")

        result = validate_config(str(config_path))
        assert result.valid is False
        assert any("YAML" in e.message or "parse" in e.message.lower() for e in result.errors)

    def test_nonexistent_config_file(self) -> None:
        """Non-existent config file path produces an error."""
        result = validate_config("/tmp/nonexistent_path_xyz_12345/config.yaml")
        assert result.valid is False
        assert any(
            "not found" in e.message.lower() or "No config" in e.message for e in result.errors
        )

    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        """Completely empty YAML file produces an error."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("")

        result = validate_config(str(config_path))
        assert result.valid is False
        assert any("empty" in e.message.lower() for e in result.errors)


class TestValidationResult:
    """Test the ValidationResult helper properties."""

    def test_errors_property(self) -> None:
        """errors property filters correctly."""
        from mk.config.validate import ValidationIssue

        result = ValidationResult(
            issues=[
                ValidationIssue(level="error", field="a", message="bad"),
                ValidationIssue(level="warning", field="b", message="hmm"),
                ValidationIssue(level="error", field="c", message="also bad"),
            ]
        )
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
