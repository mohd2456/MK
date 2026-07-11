"""Policy rules — declarative safety constraints.

A policy rule defines:
- WHAT it matches (tool, action, arguments pattern)
- WHAT it requires (preconditions that must be true)
- WHAT happens if violated (deny, warn, require confirmation)
- Rate limits (how often an action can happen)

Rules are loaded from YAML and evaluated at runtime against
every tool call before execution. They're the guardrails.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class PolicyDecision(str, Enum):
    """What the policy engine decides about an action."""

    ALLOW = "allow"  # Action is permitted
    DENY = "deny"  # Action is blocked
    REQUIRE_CONFIRM = "require_confirm"  # User must confirm
    REQUIRE_SNAPSHOT = "require_snapshot"  # Must snapshot before proceeding
    WARN = "warn"  # Allow but log a warning
    RATE_LIMITED = "rate_limited"  # Exceeded rate limit


class PolicyAction(str, Enum):
    """What to do when a rule matches."""

    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"
    SNAPSHOT = "snapshot"
    WARN = "warn"


@dataclass
class PolicyMatch:
    """Conditions for when a rule applies.

    All specified conditions must match (AND logic).
    Unspecified conditions are wildcards (match anything).
    """

    tool: Optional[str] = None  # Tool name pattern (glob)
    action: Optional[str] = None  # Action within the tool
    args_pattern: Dict[str, str] = field(default_factory=dict)  # Arg key→regex
    command_pattern: Optional[str] = None  # Regex for command strings
    agent: Optional[str] = None  # Which sub-agent is executing
    is_dangerous: Optional[bool] = None  # Match on dangerous flag

    def matches(
        self,
        tool: str = "",
        action: str = "",
        args: Optional[Dict[str, Any]] = None,
        command: str = "",
        agent: str = "",
        dangerous: bool = False,
    ) -> bool:
        """Check if this match condition applies to the given context.

        Args:
            tool: Tool being invoked.
            action: Action within the tool.
            args: Tool arguments.
            command: Raw command string (if applicable).
            agent: Sub-agent executing this.
            dangerous: Whether the task is marked dangerous.

        Returns:
            True if all specified conditions match.
        """
        args = args or {}

        # Tool match (supports glob-like patterns)
        if self.tool:
            if not self._glob_match(tool, self.tool):
                return False

        # Action match
        if self.action:
            if not self._glob_match(action, self.action):
                return False

        # Args pattern matching
        for key, pattern in self.args_pattern.items():
            value = str(args.get(key, ""))
            if not re.search(pattern, value, re.IGNORECASE):
                return False

        # Command pattern
        if self.command_pattern:
            if not re.search(self.command_pattern, command, re.IGNORECASE):
                return False

        # Agent match
        if self.agent:
            if agent != self.agent:
                return False

        # Dangerous flag
        if self.is_dangerous is not None:
            if dangerous != self.is_dangerous:
                return False

        return True

    @staticmethod
    def _glob_match(value: str, pattern: str) -> bool:
        """Simple glob matching (supports * wildcard)."""
        if pattern == "*":
            return True
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.match(regex, value, re.IGNORECASE))
        return value.lower() == pattern.lower()


@dataclass
class RateLimit:
    """Rate limiting configuration for a rule."""

    count: int = 3  # Maximum invocations
    period_seconds: int = 3600  # Time window (default: 1 hour)
    per: str = ""  # What to track per (e.g., "container", "machine")
    message: str = ""  # Message when limit exceeded

    # Runtime tracking
    _invocations: Dict[str, List[float]] = field(default_factory=dict)

    def check(self, key: str = "_global") -> bool:
        """Check if the rate limit allows another invocation.

        Args:
            key: The tracking key (e.g., container name).

        Returns:
            True if allowed, False if rate limited.
        """
        now = time.time()
        cutoff = now - self.period_seconds

        if key not in self._invocations:
            self._invocations[key] = []

        # Remove expired entries
        self._invocations[key] = [t for t in self._invocations[key] if t > cutoff]

        return len(self._invocations[key]) < self.count

    def record(self, key: str = "_global") -> None:
        """Record an invocation."""
        if key not in self._invocations:
            self._invocations[key] = []
        self._invocations[key].append(time.time())

    def remaining(self, key: str = "_global") -> int:
        """How many invocations remain in the current window."""
        now = time.time()
        cutoff = now - self.period_seconds
        current = [t for t in self._invocations.get(key, []) if t > cutoff]
        return max(0, self.count - len(current))


@dataclass
class PolicyRule:
    """A single policy rule.

    Combines matching conditions with the action to take and
    optional rate limiting. Rules are evaluated in priority order
    (higher priority = evaluated first).
    """

    name: str
    description: str = ""
    match: PolicyMatch = field(default_factory=PolicyMatch)
    action: PolicyAction = PolicyAction.DENY
    priority: int = 0  # Higher = evaluated first
    enabled: bool = True

    # Requirements (conditions that must be true for ALLOW)
    requirements: List[str] = field(default_factory=list)

    # Rate limiting
    rate_limit: Optional[RateLimit] = None

    # Messages
    deny_message: str = ""
    confirm_message: str = ""
    warn_message: str = ""

    # Snapshot configuration
    snapshot_target: Optional[str] = None  # What to snapshot before allowing
    rollback_command: Optional[str] = None  # How to undo

    def evaluate(
        self,
        tool: str = "",
        action: str = "",
        args: Optional[Dict[str, Any]] = None,
        command: str = "",
        agent: str = "",
        dangerous: bool = False,
    ) -> Optional[PolicyDecision]:
        """Evaluate this rule against an action.

        Returns None if the rule doesn't match.
        Returns a PolicyDecision if it does match.

        Args:
            tool: Tool being invoked.
            action: Action within the tool.
            args: Tool arguments.
            command: Raw command string.
            agent: Sub-agent name.
            dangerous: Whether marked dangerous.

        Returns:
            PolicyDecision if rule matches, None otherwise.
        """
        if not self.enabled:
            return None

        if not self.match.matches(tool, action, args, command, agent, dangerous):
            return None

        # Check rate limit
        if self.rate_limit:
            # Determine the tracking key
            key = "_global"
            if self.rate_limit.per and args:
                key = str(args.get(self.rate_limit.per, "_global"))

            if not self.rate_limit.check(key):
                return PolicyDecision.RATE_LIMITED

        # Return the configured action as a decision
        action_to_decision = {
            PolicyAction.ALLOW: PolicyDecision.ALLOW,
            PolicyAction.DENY: PolicyDecision.DENY,
            PolicyAction.CONFIRM: PolicyDecision.REQUIRE_CONFIRM,
            PolicyAction.SNAPSHOT: PolicyDecision.REQUIRE_SNAPSHOT,
            PolicyAction.WARN: PolicyDecision.WARN,
        }
        return action_to_decision.get(self.action, PolicyDecision.DENY)

    def record_invocation(self, args: Optional[Dict[str, Any]] = None) -> None:
        """Record that this rule's action was invoked (for rate limiting)."""
        if self.rate_limit:
            key = "_global"
            if self.rate_limit.per and args:
                key = str(args.get(self.rate_limit.per, "_global"))
            self.rate_limit.record(key)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        """Create a PolicyRule from a dictionary (parsed YAML).

        Args:
            data: Rule dictionary from YAML.

        Returns:
            PolicyRule instance.
        """
        # Parse match conditions
        match_data = data.get("match", {})
        match = PolicyMatch(
            tool=match_data.get("tool"),
            action=match_data.get("action"),
            args_pattern=match_data.get("args_pattern", {}),
            command_pattern=match_data.get("command_pattern"),
            agent=match_data.get("agent"),
            is_dangerous=match_data.get("is_dangerous"),
        )

        # Parse rate limit
        rate_limit_data = data.get("rate_limit") or data.get("limit")
        rate_limit = None
        if rate_limit_data:
            period = rate_limit_data.get("period_seconds", 3600)
            # Support "1h", "30m" format
            period_str = rate_limit_data.get("period", "")
            if period_str:
                period = cls._parse_duration(period_str)

            rate_limit = RateLimit(
                count=rate_limit_data.get("count", 3),
                period_seconds=period,
                per=rate_limit_data.get("per", ""),
                message=rate_limit_data.get("message", ""),
            )

        # Parse action
        action_str = data.get("action", "deny")
        action = (
            PolicyAction(action_str)
            if action_str in PolicyAction.__members__.values()
            else PolicyAction.DENY
        )

        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            match=match,
            action=action,
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            requirements=data.get("requirements", data.get("require", [])),
            rate_limit=rate_limit,
            deny_message=data.get("deny_message", data.get("on_deny", "")),
            confirm_message=data.get("confirm_message", data.get("on_confirm", "")),
            warn_message=data.get("warn_message", data.get("on_warn", "")),
            snapshot_target=data.get("snapshot_target"),
            rollback_command=data.get("rollback_command"),
        )

    @staticmethod
    def _parse_duration(s: str) -> int:
        """Parse a duration string like '1h', '30m', '7d' into seconds."""
        s = s.strip().lower()
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        for suffix, mult in multipliers.items():
            if s.endswith(suffix):
                try:
                    return int(s[:-1]) * mult
                except ValueError:
                    pass
        try:
            return int(s)
        except ValueError:
            return 3600  # Default to 1 hour


def load_policies(path: str) -> List[PolicyRule]:
    """Load policies from a YAML file.

    Args:
        path: Path to the policies YAML file.

    Returns:
        List of PolicyRule instances.
    """
    policy_path = Path(path)
    if not policy_path.exists():
        return []

    with open(policy_path, "r") as f:
        data = yaml.safe_load(f)

    if not data:
        return []

    # Support both list format and dict with 'policies' key
    if isinstance(data, list):
        rules_data = data
    elif isinstance(data, dict):
        rules_data = data.get("policies", data.get("rules", []))
    else:
        return []

    rules = []
    for rule_data in rules_data:
        try:
            rule = PolicyRule.from_dict(rule_data)
            rules.append(rule)
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Failed to parse policy rule: {e}")

    return rules
