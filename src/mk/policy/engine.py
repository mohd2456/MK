"""Policy engine — evaluates actions against loaded rules.

The engine is the runtime component that sits in the execution path.
Before any tool call, the engine evaluates it against all loaded
policies and returns a decision: allow, deny, confirm, or snapshot.

Evaluation order:
1. Rules evaluated by priority (highest first)
2. First matching rule wins (short-circuit)
3. If no rule matches → default policy (configurable: allow or deny)
4. Rate limits checked after match

The engine also provides the "change preview" — before execution,
it tells the user exactly what will change and what policies apply.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mk.policy.rules import (
    PolicyAction,
    PolicyDecision,
    PolicyRule,
    load_policies,
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of evaluating an action against policies.

    Contains the decision, which rule triggered it, and any
    messages to show the user.
    """

    decision: PolicyDecision
    rule_name: Optional[str] = None
    message: str = ""
    requirements: List[str] = field(default_factory=list)
    snapshot_target: Optional[str] = None
    rollback_command: Optional[str] = None

    @property
    def is_allowed(self) -> bool:
        """Whether the action can proceed."""
        return self.decision in (PolicyDecision.ALLOW, PolicyDecision.WARN)

    @property
    def needs_confirmation(self) -> bool:
        """Whether user confirmation is needed."""
        return self.decision == PolicyDecision.REQUIRE_CONFIRM

    @property
    def needs_snapshot(self) -> bool:
        """Whether a snapshot is required before proceeding."""
        return self.decision == PolicyDecision.REQUIRE_SNAPSHOT

    @property
    def is_denied(self) -> bool:
        """Whether the action is blocked."""
        return self.decision in (PolicyDecision.DENY, PolicyDecision.RATE_LIMITED)

    def format_for_user(self) -> str:
        """Format the result for user display."""
        if self.is_allowed:
            if self.decision == PolicyDecision.WARN:
                return f"⚠️ Warning: {self.message}"
            return ""

        if self.needs_confirmation:
            return f"⚡ Confirmation required: {self.message}"

        if self.needs_snapshot:
            return f"📸 Snapshot required before proceeding: {self.message}"

        if self.decision == PolicyDecision.RATE_LIMITED:
            return f"🚫 Rate limited: {self.message}"

        return f"🛑 Denied: {self.message}"


class PolicyEngine:
    """Evaluates tool calls against loaded policy rules.

    The engine is initialized with policy files and then queried
    before each tool execution. It's designed to be fast — policies
    are compiled once and evaluated with short-circuit logic.

    Usage:
        engine = PolicyEngine(policy_paths=["/etc/mk/policies.yaml"])
        result = engine.evaluate(tool="docker", action="restart", args={"container": "plex"})
        if result.is_denied:
            # Block execution
        elif result.needs_confirmation:
            # Ask user
    """

    def __init__(
        self,
        policy_paths: Optional[List[str]] = None,
        default_decision: PolicyDecision = PolicyDecision.ALLOW,
    ) -> None:
        """Initialize the policy engine.

        Args:
            policy_paths: Paths to policy YAML files.
            default_decision: Decision when no rule matches.
        """
        self._rules: List[PolicyRule] = []
        self._default_decision = default_decision
        self._evaluation_count: int = 0
        self._deny_count: int = 0
        self._policy_paths = policy_paths or []

        # Load policies from files
        for path in self._policy_paths:
            self._rules.extend(load_policies(path))

        # Sort by priority (highest first)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

        # Register built-in safety rules
        self._register_builtins()

        logger.info(f"Policy engine loaded: {len(self._rules)} rules")

    @property
    def rule_count(self) -> int:
        """Number of loaded rules."""
        return len(self._rules)

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a rule dynamically.

        Args:
            rule: The rule to add.
        """
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name.

        Args:
            name: Rule name to remove.

        Returns:
            True if found and removed.
        """
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def evaluate(
        self,
        tool: str = "",
        action: str = "",
        args: Optional[Dict[str, Any]] = None,
        command: str = "",
        agent: str = "",
        dangerous: bool = False,
    ) -> EvaluationResult:
        """Evaluate an action against all policies.

        First matching rule (by priority) determines the outcome.
        If no rule matches, the default decision applies.

        Args:
            tool: Tool being invoked.
            action: Action within the tool.
            args: Tool arguments.
            command: Raw command string (for shell commands).
            agent: Which sub-agent is executing.
            dangerous: Whether the task is marked dangerous.

        Returns:
            EvaluationResult with the decision and details.
        """
        self._evaluation_count += 1
        args = args or {}

        # Also check command inside args
        if not command and "command" in args:
            command = str(args["command"])

        for rule in self._rules:
            decision = rule.evaluate(
                tool=tool,
                action=action,
                args=args,
                command=command,
                agent=agent,
                dangerous=dangerous,
            )

            if decision is not None:
                # Rule matched
                if decision in (PolicyDecision.DENY, PolicyDecision.RATE_LIMITED):
                    self._deny_count += 1

                # Record invocation for rate limiting
                if decision == PolicyDecision.ALLOW:
                    rule.record_invocation(args)

                message = self._get_message(rule, decision)

                return EvaluationResult(
                    decision=decision,
                    rule_name=rule.name,
                    message=message,
                    requirements=rule.requirements,
                    snapshot_target=rule.snapshot_target,
                    rollback_command=rule.rollback_command,
                )

        # No rule matched — use default
        return EvaluationResult(
            decision=self._default_decision,
            message="No policy rule matched — using default",
        )

    def evaluate_command(self, command: str, agent: str = "") -> EvaluationResult:
        """Convenience: evaluate a raw shell command.

        Args:
            command: The shell command string.
            agent: Which agent is running it.

        Returns:
            EvaluationResult.
        """
        return self.evaluate(
            tool="ssh",
            action="run_command",
            args={"command": command},
            command=command,
            agent=agent,
        )

    def get_applicable_rules(
        self,
        tool: str = "",
        action: str = "",
    ) -> List[PolicyRule]:
        """Get all rules that would match a given tool/action.

        Useful for "what rules apply to this tool?" queries.

        Args:
            tool: Tool name.
            action: Action name.

        Returns:
            List of matching rules.
        """
        matching = []
        for rule in self._rules:
            if rule.match.matches(tool=tool, action=action):
                matching.append(rule)
        return matching

    def _get_message(self, rule: PolicyRule, decision: PolicyDecision) -> str:
        """Get the appropriate message for a decision."""
        if decision == PolicyDecision.DENY:
            return rule.deny_message or f"Blocked by policy: {rule.name}"
        elif decision == PolicyDecision.REQUIRE_CONFIRM:
            return rule.confirm_message or f"Policy '{rule.name}' requires confirmation"
        elif decision == PolicyDecision.WARN:
            return rule.warn_message or f"Policy warning: {rule.name}"
        elif decision == PolicyDecision.RATE_LIMITED:
            if rule.rate_limit and rule.rate_limit.message:
                return rule.rate_limit.message
            return f"Rate limited by policy: {rule.name}"
        elif decision == PolicyDecision.REQUIRE_SNAPSHOT:
            return f"Policy '{rule.name}' requires a snapshot before proceeding"
        return ""

    def _register_builtins(self) -> None:
        """Register built-in safety policies.

        These are the baseline rules that always apply unless
        explicitly overridden by a higher-priority user rule.
        """
        from mk.policy.rules import PolicyMatch, RateLimit

        builtins = [
            # Block recursive deletion outside safe paths
            PolicyRule(
                name="builtin:no-recursive-delete",
                description="Block rm -rf outside /tmp",
                match=PolicyMatch(command_pattern=r"rm\s+-(rf|fr)\s+/(?!tmp)"),
                action=PolicyAction.DENY,
                priority=-100,
                deny_message="Recursive deletion outside /tmp is blocked. Create a snapshot first.",
            ),
            # Block disk formatting
            PolicyRule(
                name="builtin:no-disk-format",
                description="Block filesystem formatting",
                match=PolicyMatch(command_pattern=r"mkfs|fdisk|parted"),
                action=PolicyAction.DENY,
                priority=-100,
                deny_message="Disk formatting is blocked by default policy.",
            ),
            # Require confirmation for service stops
            PolicyRule(
                name="builtin:confirm-service-stop",
                description="Confirm before stopping services",
                match=PolicyMatch(
                    command_pattern=r"systemctl\s+(stop|disable|mask)"
                ),
                action=PolicyAction.CONFIRM,
                priority=-90,
                confirm_message="Stopping a system service — confirm?",
            ),
            # Require confirmation for container removal
            PolicyRule(
                name="builtin:confirm-container-remove",
                description="Confirm before removing containers",
                match=PolicyMatch(
                    tool="docker",
                    action="remove",
                ),
                action=PolicyAction.CONFIRM,
                priority=-90,
                confirm_message="Removing a container permanently — confirm?",
            ),
            # Rate limit container restarts
            PolicyRule(
                name="builtin:restart-rate-limit",
                description="Limit container restarts to 5 per hour",
                match=PolicyMatch(
                    tool="docker",
                    action="restart",
                ),
                action=PolicyAction.ALLOW,
                priority=-80,
                rate_limit=RateLimit(
                    count=5,
                    period_seconds=3600,
                    per="container_name",
                    message="Container restarted too many times — investigate root cause",
                ),
            ),
            # Snapshot before ZFS destroy
            PolicyRule(
                name="builtin:snapshot-before-destroy",
                description="Require snapshot before ZFS destroy",
                match=PolicyMatch(command_pattern=r"zfs\s+destroy"),
                action=PolicyAction.SNAPSHOT,
                priority=-85,
                snapshot_target="parent_dataset",
                rollback_command="zfs rollback {snapshot}",
            ),
            # Block shutdown without confirmation
            PolicyRule(
                name="builtin:confirm-shutdown",
                description="Require confirmation for server shutdown",
                match=PolicyMatch(command_pattern=r"shutdown|poweroff|halt|reboot"),
                action=PolicyAction.CONFIRM,
                priority=-90,
                confirm_message="This will take the server offline — are you sure?",
            ),
            # Warn on public exposure
            PolicyRule(
                name="builtin:warn-public-expose",
                description="Warn when exposing services publicly",
                match=PolicyMatch(command_pattern=r"0\.0\.0\.0|--publish.*:0\.0\.0\.0"),
                action=PolicyAction.CONFIRM,
                priority=-85,
                confirm_message="This exposes a service to all network interfaces (public). Confirm?",
            ),
        ]

        # Only add builtins if no user rules override them
        existing_names = {r.name for r in self._rules}
        for rule in builtins:
            if rule.name not in existing_names:
                self._rules.append(rule)

    def get_status(self) -> Dict[str, Any]:
        """Get engine status and statistics."""
        return {
            "total_rules": self.rule_count,
            "builtin_rules": sum(1 for r in self._rules if r.name.startswith("builtin:")),
            "user_rules": sum(1 for r in self._rules if not r.name.startswith("builtin:")),
            "evaluations": self._evaluation_count,
            "denials": self._deny_count,
            "denial_rate": (
                self._deny_count / self._evaluation_count
                if self._evaluation_count > 0
                else 0.0
            ),
        }


