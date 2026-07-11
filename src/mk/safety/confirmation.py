"""Confirmation system for dangerous actions.

Maintains a configurable list of dangerous action patterns and
requires explicit user confirmation before executing them.
Protects against accidental or malicious destructive operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# Default patterns that indicate dangerous operations
DEFAULT_DANGEROUS_PATTERNS: List[str] = [
    r"\brm\s+-rf\b",
    r"\brm\s+-r\b",
    r"\brm\s+--recursive\b",
    r"\brmdir\b",
    r"\bdelete\b",
    r"\bwipe\b",
    r"\bdrop\s+database\b",
    r"\bdrop\s+table\b",
    r"\btruncate\b",
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bsystemctl\s+(stop|disable|mask)\b",
    r"\bkill\s+-9\b",
    r"\bkillall\b",
    r"\bchmod\s+777\b",
    r"\bchown\s+-R\b",
    r"\biptables\s+-F\b",
    r"\biptables\s+--flush\b",
    r"\bgit\s+push\s+--force\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bcurl\b.*\|\s*(ba)?sh\b",
    r"\bwget\b.*\|\s*(ba)?sh\b",
    r"\b>\s*/dev/sd[a-z]\b",
    r"\bfdisk\b",
    r"\bparted\b",
]


@dataclass
class ConfirmationResult:
    """Result of a confirmation request."""

    confirmed: bool
    action_description: str
    reason: Optional[str] = None


@dataclass
class ConfirmationManager:
    """Manages confirmation prompts for dangerous actions.

    Checks proposed tool calls and commands against a set of
    dangerous patterns and requires explicit confirmation before
    allowing execution.

    Attributes:
        patterns: List of regex patterns identifying dangerous actions.
        auto_confirm: If True, all actions are auto-confirmed (for testing).
        confirmation_callback: Optional callback for requesting user confirmation.
    """

    patterns: List[str] = field(default_factory=lambda: list(DEFAULT_DANGEROUS_PATTERNS))
    auto_confirm: bool = False
    confirmation_callback: Optional[Callable[[str], bool]] = None

    def __post_init__(self) -> None:
        """Compile regex patterns for efficient matching."""
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def is_dangerous(self, command: str) -> bool:
        """Check if a command matches any dangerous action pattern.

        Args:
            command: The command string or action description to check.

        Returns:
            True if the command matches a dangerous pattern.
        """
        for pattern in self._compiled_patterns:
            if pattern.search(command):
                return True
        return False

    def get_matching_patterns(self, command: str) -> List[str]:
        """Get all dangerous patterns that match the given command.

        Args:
            command: The command string to check.

        Returns:
            List of pattern strings that matched.
        """
        matches = []
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(command):
                matches.append(self.patterns[i])
        return matches

    def add_pattern(self, pattern: str) -> None:
        """Add a new dangerous action pattern.

        Args:
            pattern: Regex pattern string to add.
        """
        self.patterns.append(pattern)
        self._compiled_patterns.append(re.compile(pattern, re.IGNORECASE))

    def remove_pattern(self, pattern: str) -> bool:
        """Remove a dangerous action pattern.

        Args:
            pattern: The exact pattern string to remove.

        Returns:
            True if the pattern was found and removed.
        """
        try:
            idx = self.patterns.index(pattern)
            self.patterns.pop(idx)
            self._compiled_patterns.pop(idx)
            return True
        except ValueError:
            return False

    def request_confirmation(self, action_description: str) -> ConfirmationResult:
        """Request confirmation for a dangerous action.

        Uses the configured confirmation callback, or auto_confirm setting.

        Args:
            action_description: Human-readable description of the action.

        Returns:
            ConfirmationResult indicating whether the action was confirmed.
        """
        if self.auto_confirm:
            return ConfirmationResult(
                confirmed=True,
                action_description=action_description,
                reason="auto-confirmed",
            )

        if self.confirmation_callback:
            confirmed = self.confirmation_callback(action_description)
            return ConfirmationResult(
                confirmed=confirmed,
                action_description=action_description,
                reason="user-response",
            )

        # Default: deny if no callback is configured
        return ConfirmationResult(
            confirmed=False,
            action_description=action_description,
            reason="no confirmation handler configured",
        )

    def check_and_confirm(self, command: str) -> ConfirmationResult:
        """Check if a command is dangerous and request confirmation if needed.

        Args:
            command: The command to check and potentially confirm.

        Returns:
            ConfirmationResult. If the command is not dangerous,
            returns confirmed=True automatically.
        """
        if not self.is_dangerous(command):
            return ConfirmationResult(
                confirmed=True,
                action_description=command,
                reason="not-dangerous",
            )
        return self.request_confirmation(command)
