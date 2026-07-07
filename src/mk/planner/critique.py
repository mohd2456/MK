"""Critique Gate — Pre-execution plan review.

Before anything risky runs, the critique gate reviews it:
- Is this reversible?
- What's the blast radius if it fails?
- Are there dependencies that would be affected?
- Does this conflict with anything currently running?
- Should the user be asked for confirmation?

The critique gate is NOT a full LLM call (too expensive to call for every task).
It uses a combination of:
1. Rule-based risk assessment (fast, free)
2. Graph-based dependency analysis (uses the knowledge graph)
3. Optional LLM review (only for high-risk plans)

Think of it as a senior engineer glancing at a PR before merging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from mk.planner.graph import TaskGraph, TaskNode


class RiskLevel(str, Enum):
    """Risk level assessment for a plan or task.

    Ordered from lowest to highest severity. Use .severity for comparison.
    """

    SAFE = "safe"            # No concerns, proceed automatically
    LOW = "low"              # Minor risk, proceed with logging
    MEDIUM = "medium"        # Moderate risk, notify user
    HIGH = "high"            # Significant risk, require confirmation
    CRITICAL = "critical"    # Extreme risk, block without explicit override

    @property
    def severity(self) -> int:
        """Numeric severity for comparison (higher = more dangerous)."""
        return {"safe": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]

    def __gt__(self, other: "RiskLevel") -> bool:
        return self.severity > other.severity

    def __ge__(self, other: "RiskLevel") -> bool:
        return self.severity >= other.severity

    def __lt__(self, other: "RiskLevel") -> bool:
        return self.severity < other.severity

    def __le__(self, other: "RiskLevel") -> bool:
        return self.severity <= other.severity


@dataclass
class CritiqueResult:
    """Result of the critique gate's review.

    Contains the risk assessment, specific concerns, and
    a decision on whether to proceed.
    """

    approved: bool = True
    risk_level: RiskLevel = RiskLevel.SAFE
    concerns: List[str] = field(default_factory=list)
    blocked_tasks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_message: str = ""
    blast_radius: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_safe(self) -> bool:
        """Whether the plan is considered safe to execute automatically."""
        return self.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)

    @property
    def needs_user(self) -> bool:
        """Whether the user needs to be involved."""
        return self.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or self.requires_confirmation

    def summary(self) -> str:
        """Human-readable summary of the critique."""
        lines = [f"Risk: {self.risk_level.value.upper()}"]

        if self.concerns:
            lines.append("Concerns:")
            for c in self.concerns:
                lines.append(f"  - {c}")

        if self.blocked_tasks:
            lines.append(f"Blocked tasks: {', '.join(self.blocked_tasks)}")

        if self.recommendations:
            lines.append("Recommendations:")
            for r in self.recommendations:
                lines.append(f"  → {r}")

        if self.blast_radius:
            lines.append(f"Blast radius: {self.blast_radius}")

        return "\n".join(lines)


# Risk patterns — commands/actions and their risk levels
RISK_PATTERNS: List[Dict[str, Any]] = [
    # Critical: irreversible data destruction
    {"pattern": r"rm\s+-rf\s+/(?!tmp)", "level": RiskLevel.CRITICAL, "reason": "Recursive delete outside /tmp"},
    {"pattern": r"zfs\s+destroy", "level": RiskLevel.CRITICAL, "reason": "ZFS dataset destruction"},
    {"pattern": r"dd\s+if=.+of=/dev/", "level": RiskLevel.CRITICAL, "reason": "Raw disk write"},
    {"pattern": r"mkfs", "level": RiskLevel.CRITICAL, "reason": "Filesystem format"},
    {"pattern": r"drop\s+(database|table)", "level": RiskLevel.CRITICAL, "reason": "Database destruction"},

    # High: service disruption, security changes
    {"pattern": r"shutdown|poweroff|halt", "level": RiskLevel.HIGH, "reason": "Server shutdown"},
    {"pattern": r"systemctl\s+(stop|disable|mask)", "level": RiskLevel.HIGH, "reason": "Service disruption"},
    {"pattern": r"docker\s+rm\s+-f", "level": RiskLevel.HIGH, "reason": "Force container removal"},
    {"pattern": r"iptables\s+-F", "level": RiskLevel.HIGH, "reason": "Firewall flush"},
    {"pattern": r"chmod\s+777", "level": RiskLevel.HIGH, "reason": "World-writable permissions"},
    {"pattern": r"expose.*0\.0\.0\.0", "level": RiskLevel.HIGH, "reason": "Public internet exposure"},

    # Medium: state changes that could cause issues
    {"pattern": r"docker\s+(stop|restart)", "level": RiskLevel.MEDIUM, "reason": "Container state change"},
    {"pattern": r"systemctl\s+restart", "level": RiskLevel.MEDIUM, "reason": "Service restart"},
    {"pattern": r"apt\s+(remove|purge)", "level": RiskLevel.MEDIUM, "reason": "Package removal"},
    {"pattern": r"git\s+push\s+--force", "level": RiskLevel.MEDIUM, "reason": "Force push"},
    {"pattern": r"rsync.*--delete", "level": RiskLevel.MEDIUM, "reason": "Rsync with delete (removes files at destination)"},

    # Low: observable changes that are generally safe
    {"pattern": r"docker\s+pull", "level": RiskLevel.LOW, "reason": "Image pull (bandwidth/disk)"},
    {"pattern": r"apt\s+(update|upgrade)", "level": RiskLevel.LOW, "reason": "System update"},
]


class CritiqueGate:
    """Pre-execution plan reviewer.

    Reviews task graphs before execution to identify risks,
    assess blast radius, and decide whether to proceed,
    require confirmation, or block.

    The gate is conservative by default — it's easier to
    approve a blocked plan than to undo a catastrophe.
    """

    def __init__(
        self,
        auto_approve_safe: bool = True,
        auto_approve_low: bool = True,
        knowledge_graph: Optional[Any] = None,
    ) -> None:
        """Initialize the critique gate.

        Args:
            auto_approve_safe: Auto-approve SAFE risk tasks.
            auto_approve_low: Auto-approve LOW risk tasks.
            knowledge_graph: Optional knowledge graph for dependency analysis.
        """
        self._auto_approve_safe = auto_approve_safe
        self._auto_approve_low = auto_approve_low
        self._graph = knowledge_graph
        self._compiled_patterns = [
            (re.compile(p["pattern"], re.IGNORECASE), p["level"], p["reason"])
            for p in RISK_PATTERNS
        ]

    def review_plan(self, task_graph: TaskGraph) -> CritiqueResult:
        """Review an entire task graph before execution.

        Analyzes all tasks, their relationships, and the overall
        plan for risk factors.

        Args:
            task_graph: The plan to review.

        Returns:
            CritiqueResult with the assessment.
        """
        concerns: List[str] = []
        blocked: List[str] = []
        recommendations: List[str] = []
        max_risk = RiskLevel.SAFE
        blast_radius: Dict[str, Any] = {}

        for task in task_graph.nodes.values():
            task_risk = self._assess_task_risk(task)

            if task_risk.risk_level > max_risk:
                max_risk = task_risk.risk_level

            concerns.extend(task_risk.concerns)

            if task_risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                blocked.append(task.id)
                task.mark_blocked(
                    f"Critique gate: {task_risk.concerns[0] if task_risk.concerns else 'high risk'}"
                )

        # Check for dangerous task chains
        chain_concerns = self._check_dangerous_chains(task_graph)
        concerns.extend(chain_concerns)

        # Assess overall blast radius
        if task_graph.dangerous_tasks:
            blast_radius = self._assess_blast_radius(task_graph)

        # Generate recommendations
        if max_risk >= RiskLevel.MEDIUM:
            recommendations.append("Consider creating a snapshot/backup before proceeding")
        if len(task_graph.nodes) > 10:
            recommendations.append("Large plan — consider executing in stages")
        if any(t.max_retries == 0 for t in task_graph.nodes.values() if t.is_dangerous):
            recommendations.append("Dangerous tasks should have retries disabled (already done)")

        # Determine approval
        requires_confirmation = max_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        approved = self._should_approve(max_risk)

        confirmation_message = ""
        if requires_confirmation:
            dangerous_names = [t.name for t in task_graph.dangerous_tasks]
            confirmation_message = (
                f"This plan contains {len(dangerous_names)} high-risk actions: "
                f"{', '.join(dangerous_names)}. Proceed?"
            )

        return CritiqueResult(
            approved=approved,
            risk_level=max_risk,
            concerns=concerns,
            blocked_tasks=blocked,
            recommendations=recommendations,
            requires_confirmation=requires_confirmation,
            confirmation_message=confirmation_message,
            blast_radius=blast_radius,
        )

    def review_task(self, task: TaskNode) -> CritiqueResult:
        """Review a single task (used during execution for re-checks).

        Args:
            task: The task to review.

        Returns:
            CritiqueResult for this specific task.
        """
        result = self._assess_task_risk(task)
        result.approved = self._should_approve(result.risk_level)
        return result

    def _assess_task_risk(self, task: TaskNode) -> CritiqueResult:
        """Assess the risk level of a single task.

        Args:
            task: The task to assess.

        Returns:
            CritiqueResult with risk assessment.
        """
        concerns: List[str] = []
        max_risk = RiskLevel.SAFE

        # Check if marked dangerous
        if task.is_dangerous:
            max_risk = RiskLevel.HIGH
            if task.risk_description:
                concerns.append(f"[{task.name}] {task.risk_description}")
            else:
                concerns.append(f"[{task.name}] Marked as dangerous")

        # Check tool args for risky patterns
        risk_text = self._get_risk_text(task)
        for pattern, level, reason in self._compiled_patterns:
            if pattern.search(risk_text):
                if level.value > max_risk.value:
                    max_risk = level
                concerns.append(f"[{task.name}] {reason}")

        return CritiqueResult(
            risk_level=max_risk,
            concerns=concerns,
        )

    def _get_risk_text(self, task: TaskNode) -> str:
        """Extract text from a task to check against risk patterns.

        Combines the tool args, prompt, and description into a single
        string for pattern matching.
        """
        parts: List[str] = []
        if task.prompt:
            parts.append(task.prompt)
        if task.description:
            parts.append(task.description)
        if task.tool:
            parts.append(task.tool)
        for key, value in task.tool_args.items():
            if isinstance(value, str):
                parts.append(value)
        return " ".join(parts)

    def _check_dangerous_chains(self, graph: TaskGraph) -> List[str]:
        """Check for dangerous patterns in task chains.

        For example: delete + no backup step before it.
        """
        concerns: List[str] = []

        dangerous = graph.dangerous_tasks
        if not dangerous:
            return concerns

        # Check: is there a backup/snapshot step before dangerous tasks?
        has_backup_step = any(
            "backup" in t.name.lower() or "snapshot" in t.name.lower()
            for t in graph.nodes.values()
        )

        if not has_backup_step and len(dangerous) > 0:
            concerns.append(
                "Plan has dangerous actions but no backup/snapshot step"
            )

        # Check: multiple dangerous tasks in the same wave (parallel risk)
        waves = graph.execution_order()
        for i, wave in enumerate(waves):
            dangerous_in_wave = [
                tid for tid in wave
                if graph.nodes[tid].is_dangerous
            ]
            if len(dangerous_in_wave) > 1:
                concerns.append(
                    f"Wave {i+1} has {len(dangerous_in_wave)} dangerous tasks running in parallel"
                )

        return concerns

    def _assess_blast_radius(self, graph: TaskGraph) -> Dict[str, Any]:
        """Assess what would be affected if dangerous tasks fail.

        Uses the task graph dependencies to determine downstream impact.
        """
        radius: Dict[str, Any] = {
            "dangerous_count": len(graph.dangerous_tasks),
            "affected_tasks": [],
            "services_affected": [],
        }

        for task in graph.dangerous_tasks:
            dependents = graph.get_dependents(task.id)
            if dependents:
                radius["affected_tasks"].extend([d.name for d in dependents])

            # Check if task mentions known services
            risk_text = self._get_risk_text(task)
            for service in ["plex", "sonarr", "radarr", "postgres", "nginx", "traefik"]:
                if service in risk_text.lower():
                    radius["services_affected"].append(service)

        radius["affected_tasks"] = list(set(radius["affected_tasks"]))
        radius["services_affected"] = list(set(radius["services_affected"]))

        return radius

    def _should_approve(self, risk_level: RiskLevel) -> bool:
        """Determine if a risk level should be auto-approved."""
        if risk_level == RiskLevel.SAFE and self._auto_approve_safe:
            return True
        if risk_level == RiskLevel.LOW and self._auto_approve_low:
            return True
        if risk_level == RiskLevel.MEDIUM:
            return True  # Medium proceeds with logging
        return False  # HIGH and CRITICAL require confirmation
