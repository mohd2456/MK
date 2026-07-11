"""Command router for MK.

Detects simple direct commands and routes them to tool execution WITHOUT
calling an LLM. Only uses the LLM when actual thinking/reasoning is needed.
This saves tokens, reduces cost, and speeds up simple operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class CommandPattern:
    """A registered command pattern for direct routing."""

    name: str
    patterns: List[str]
    tool_name: str
    arg_extractor: Optional[Callable[[str], Dict[str, str]]] = None
    description: str = ""


@dataclass
class RouteResult:
    """Result of the command routing decision."""

    is_direct: bool = False
    tool_name: Optional[str] = None
    tool_args: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    matched_pattern: Optional[str] = None


class CommandRouter:
    """Smart router that detects simple commands vs. complex queries.

    Simple commands (restart service, check status, etc.) are routed
    directly to tools without an LLM call. Complex queries that need
    reasoning, planning, or creative responses go to the LLM.
    """

    # Threshold above which we route directly (0.0 to 1.0)
    CONFIDENCE_THRESHOLD = 0.8

    def __init__(self) -> None:
        """Initialize the command router with default patterns."""
        self._patterns: List[CommandPattern] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default command patterns."""
        self.register_pattern(
            CommandPattern(
                name="restart_service",
                patterns=[
                    r"^restart\s+(\w[\w\-]*)",
                    r"^reboot\s+(\w[\w\-]*)",
                ],
                tool_name="restart_service",
                arg_extractor=self._extract_service_name,
                description="Restart a service or machine",
            )
        )
        self.register_pattern(
            CommandPattern(
                name="check_status",
                patterns=[
                    r"^(?:check\s+)?status\s+(?:of\s+)?(\w[\w\-]*)",
                    r"^(?:is\s+)?(\w[\w\-]*)\s+(?:up|running|alive|ok)\??",
                    r"^how\s+is\s+(\w[\w\-]*)\??$",
                ],
                tool_name="check_status",
                arg_extractor=self._extract_service_name,
                description="Check status of a service or machine",
            )
        )
        self.register_pattern(
            CommandPattern(
                name="stop_service",
                patterns=[
                    r"^stop\s+(\w[\w\-]*)",
                    r"^kill\s+(\w[\w\-]*)",
                ],
                tool_name="stop_service",
                arg_extractor=self._extract_service_name,
                description="Stop a service",
            )
        )
        self.register_pattern(
            CommandPattern(
                name="start_service",
                patterns=[
                    r"^start\s+(\w[\w\-]*)",
                ],
                tool_name="start_service",
                arg_extractor=self._extract_service_name,
                description="Start a service",
            )
        )

    def register_pattern(self, pattern: CommandPattern) -> None:
        """Register a new command pattern.

        Args:
            pattern: The CommandPattern to register.
        """
        self._patterns.append(pattern)

    def route(self, user_input: str) -> RouteResult:
        """Route user input to either direct execution or LLM.

        Analyzes the input against registered patterns and returns
        a routing decision.

        Args:
            user_input: Raw user input text.

        Returns:
            RouteResult indicating whether this is a direct command.
        """
        cleaned = user_input.strip().lower()

        # Try each registered pattern
        for cmd_pattern in self._patterns:
            match_result = self._try_match(cleaned, cmd_pattern)
            if match_result:
                return match_result

        # No pattern matched - needs LLM
        return RouteResult(is_direct=False, confidence=0.0)

    def _try_match(self, text: str, cmd_pattern: CommandPattern) -> Optional[RouteResult]:
        """Try to match input against a command pattern.

        Args:
            text: Cleaned input text.
            cmd_pattern: Pattern to try.

        Returns:
            RouteResult if matched, None otherwise.
        """
        for pattern in cmd_pattern.patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                args: Dict[str, str] = {}
                if cmd_pattern.arg_extractor:
                    args = cmd_pattern.arg_extractor(text)
                elif match.groups():
                    args = {"target": match.group(1)}

                return RouteResult(
                    is_direct=True,
                    tool_name=cmd_pattern.tool_name,
                    tool_args=args,
                    confidence=0.95,
                    matched_pattern=cmd_pattern.name,
                )
        return None

    def _extract_service_name(self, text: str) -> Dict[str, str]:
        """Extract a service/target name from command text.

        Args:
            text: The command text.

        Returns:
            Dict with the extracted target name.
        """
        # Find the last word (or hyphenated word) that looks like a name
        parts = text.strip().split()
        # Skip common verbs and prepositions
        skip_words = {
            "restart",
            "reboot",
            "check",
            "status",
            "of",
            "is",
            "start",
            "stop",
            "kill",
            "up",
            "running",
            "alive",
            "ok",
            "how",
        }
        for part in reversed(parts):
            cleaned = part.rstrip("?").rstrip(".")
            if cleaned and cleaned not in skip_words:
                return {"target": cleaned}
        return {"target": parts[-1] if parts else "unknown"}

    def is_complex_query(self, user_input: str) -> bool:
        """Determine if a query needs LLM reasoning.

        Heuristics for complexity:
        - Questions with 'why', 'how' (not 'how is X'), 'explain', 'what if'
        - Multi-sentence inputs
        - Requests for creative content
        - Anything that doesn't match a simple command pattern

        Args:
            user_input: Raw user input.

        Returns:
            True if the query needs LLM processing.
        """
        route = self.route(user_input)
        return not route.is_direct

    @property
    def registered_commands(self) -> List[Tuple[str, str]]:
        """Return list of (name, description) for all registered commands."""
        return [(p.name, p.description) for p in self._patterns]
