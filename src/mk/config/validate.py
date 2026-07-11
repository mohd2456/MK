"""Configuration validation for MK.

Loads the config.yaml file, validates it against the Pydantic schema
from settings.py, and returns structured errors and warnings. Provides
both a programmatic API and a CLI entry point.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import ValidationError

from mk.config.settings import Settings


@dataclass
class ValidationIssue:
    """A single validation issue (error or warning)."""

    level: str  # "error" or "warning"
    field: str  # Which config field has the issue
    message: str  # Human-readable description


@dataclass
class ValidationResult:
    """Result of config validation."""

    valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    config_path: Optional[str] = None

    @property
    def errors(self) -> List[ValidationIssue]:
        """Return only error-level issues."""
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Return only warning-level issues."""
        return [i for i in self.issues if i.level == "warning"]


def validate_config(config_path: Optional[str] = None) -> ValidationResult:
    """Validate the MK configuration file.

    Loads the config from the given path (or default search locations),
    validates the structure against the Pydantic schema, and performs
    semantic checks:
    - At least one LLM provider must be configured
    - Machine configs must have valid host fields
    - Safety settings must have valid paths

    Args:
        config_path: Path to config.yaml. If None, uses default search order.

    Returns:
        ValidationResult with all issues found.
    """
    result = ValidationResult()

    # Step 1: Find and load the raw YAML
    search_paths: List[Path] = []
    if config_path:
        search_paths.append(Path(config_path))
    else:
        import os

        env_config = os.environ.get("MK_CONFIG")
        if env_config:
            search_paths.append(Path(env_config))
        search_paths.extend(
            [
                Path("/etc/mk/config.yaml"),
                Path.home() / ".mk" / "config.yaml",
                Path("config.yaml"),
            ]
        )

    found_path: Optional[Path] = None
    for path in search_paths:
        if path.exists():
            found_path = path
            break

    if found_path is None:
        result.valid = False
        result.issues.append(
            ValidationIssue(
                level="error",
                field="config_file",
                message="No config file found. Searched: "
                + ", ".join(str(p) for p in search_paths),
            )
        )
        return result

    result.config_path = str(found_path)

    # Step 2: Parse YAML
    try:
        with open(found_path, "r") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.valid = False
        result.issues.append(
            ValidationIssue(
                level="error",
                field="config_file",
                message=f"YAML parse error: {e}",
            )
        )
        return result

    if not raw_data:
        if raw_data is None:
            result.valid = False
            result.issues.append(
                ValidationIssue(
                    level="error",
                    field="config_file",
                    message="Config file is empty or not a valid YAML mapping.",
                )
            )
            return result
        # Empty dict is fine - Settings has defaults for everything
        raw_data = {}
    elif not isinstance(raw_data, dict):
        result.valid = False
        result.issues.append(
            ValidationIssue(
                level="error",
                field="config_file",
                message="Config file is empty or not a valid YAML mapping.",
            )
        )
        return result

    # Step 3: Validate against Pydantic schema
    try:
        settings = Settings(**raw_data)
    except ValidationError as e:
        result.valid = False
        for error in e.errors():
            field_path = ".".join(str(loc) for loc in error["loc"])
            result.issues.append(
                ValidationIssue(
                    level="error",
                    field=field_path,
                    message=error["msg"],
                )
            )
        return result

    # Step 4: Semantic validations
    _validate_providers(settings, result)
    _validate_machines(settings, result)
    _validate_safety(settings, result)

    return result


def _validate_providers(settings: Settings, result: ValidationResult) -> None:
    """Check LLM provider configuration."""
    if not settings.llm_providers:
        result.issues.append(
            ValidationIssue(
                level="warning",
                field="llm_providers",
                message="No LLM providers configured. MK will not be able to generate responses.",
            )
        )
        return

    for i, provider in enumerate(settings.llm_providers):
        if not provider.endpoint:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    field=f"llm_providers[{i}].endpoint",
                    message=f"Provider '{provider.name}' has no endpoint configured.",
                )
            )
            result.valid = False

        if not provider.api_key_ref:
            result.issues.append(
                ValidationIssue(
                    level="warning",
                    field=f"llm_providers[{i}].api_key_ref",
                    message=f"Provider '{provider.name}' has no API key reference.",
                )
            )

        if provider.temperature < 0 or provider.temperature > 2.0:
            result.issues.append(
                ValidationIssue(
                    level="warning",
                    field=f"llm_providers[{i}].temperature",
                    message=f"Provider '{provider.name}' has unusual temperature: {provider.temperature}",
                )
            )


def _validate_machines(settings: Settings, result: ValidationResult) -> None:
    """Check machine configurations."""
    for i, machine in enumerate(settings.machines):
        if not machine.host:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    field=f"machines[{i}].host",
                    message=f"Machine '{machine.name}' has no host configured.",
                )
            )
            result.valid = False

        if machine.ssh_key_path:
            key_path = Path(machine.ssh_key_path).expanduser()
            if not key_path.exists():
                result.issues.append(
                    ValidationIssue(
                        level="warning",
                        field=f"machines[{i}].ssh_key_path",
                        message=f"SSH key path '{machine.ssh_key_path}' does not exist.",
                    )
                )


def _validate_safety(settings: Settings, result: ValidationResult) -> None:
    """Check safety settings."""
    if settings.safety.max_iterations < 1:
        result.issues.append(
            ValidationIssue(
                level="error",
                field="safety.max_iterations",
                message="max_iterations must be at least 1.",
            )
        )
        result.valid = False

    if settings.safety.max_iterations > 50:
        result.issues.append(
            ValidationIssue(
                level="warning",
                field="safety.max_iterations",
                message=f"max_iterations is very high ({settings.safety.max_iterations}). "
                "This could lead to runaway agent loops.",
            )
        )


def cli_validate() -> None:
    """CLI entry point for config validation.

    Prints validation results to stdout and exits with
    code 0 if valid, 1 if errors found.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Validate MK configuration")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to config.yaml (uses default search order if not specified)",
    )
    args = parser.parse_args()

    result = validate_config(args.config)

    if result.config_path:
        print(f"Config: {result.config_path}")
        print()

    if not result.issues:
        print("Configuration is valid. No issues found.")
        sys.exit(0)

    for issue in result.issues:
        icon = "ERROR" if issue.level == "error" else "WARN"
        print(f"  [{icon}] {issue.field}: {issue.message}")

    print()
    errors = len(result.errors)
    warnings = len(result.warnings)
    print(f"Result: {errors} error(s), {warnings} warning(s)")

    sys.exit(1 if errors > 0 else 0)
