"""Rollback handler — undo actions using pre-execution snapshots.

When an operation goes wrong, the rollback handler uses the
snapshot taken before execution to restore the previous state.
Supports:
- Single-step rollback (one snapshot → one restore)
- Multi-step rollback (composite snapshots → ordered undo)
- Dry-run mode (show what would be undone without doing it)
- Partial rollback (undo specific steps, keep others)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from mk.policy.snapshots import Snapshot, SnapshotManager, SnapshotType

logger = logging.getLogger(__name__)


@dataclass
class RollbackStep:
    """A single step in a rollback plan."""

    description: str
    command: str  # Command to execute for rollback
    target: str   # What is being rolled back
    snapshot_id: str
    order: int = 0  # Execution order (lower = first)
    executed: bool = False
    success: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class RollbackPlan:
    """A plan for undoing one or more operations.

    Contains ordered steps and can be executed in full or partially.
    """

    id: str
    description: str
    steps: List[RollbackStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    executed: bool = False
    executed_at: Optional[float] = None
    partial: bool = False  # True if only some steps executed

    @property
    def step_count(self) -> int:
        """Number of steps in the plan."""
        return len(self.steps)

    @property
    def is_empty(self) -> bool:
        """Whether the plan has no steps."""
        return len(self.steps) == 0

    def summary(self) -> str:
        """Human-readable plan summary."""
        lines = [f"Rollback Plan: {self.description}"]
        lines.append(f"Steps: {self.step_count}")
        for step in self.steps:
            status = "✓" if step.success else "✗" if step.success is False else "○"
            lines.append(f"  {status} [{step.order}] {step.description}")
            lines.append(f"       → {step.command}")
        return "\n".join(lines)

    def preview(self) -> str:
        """Show what the rollback would do (dry-run display)."""
        lines = [f"🔄 Rollback: {self.description}"]
        lines.append(f"This will undo {self.step_count} change(s):\n")
        for i, step in enumerate(self.steps, 1):
            lines.append(f"  {i}. {step.description}")
            lines.append(f"     Command: {step.command}")
            lines.append(f"     Target: {step.target}")
            lines.append("")
        return "\n".join(lines)


class RollbackHandler:
    """Handles rollback of failed operations.

    Works with the SnapshotManager to find the right snapshot
    and generate a rollback plan. Can execute the plan or just
    preview what would happen.

    Usage:
        handler = RollbackHandler(snapshot_manager)

        # After a failure:
        plan = handler.create_plan("plex container update failed", snapshot_id="snap-abc123")
        print(plan.preview())  # Show user what will be undone

        # If approved:
        result = await handler.execute_plan(plan)
    """

    def __init__(
        self,
        snapshot_manager: SnapshotManager,
        command_executor: Optional[Callable[[str], Coroutine]] = None,
    ) -> None:
        """Initialize the rollback handler.

        Args:
            snapshot_manager: The snapshot manager with stored snapshots.
            command_executor: Async function to execute rollback commands.
                Signature: async (command: str) -> str
        """
        self._snapshots = snapshot_manager
        self._executor = command_executor
        self._plans: List[RollbackPlan] = []

    def create_plan(
        self,
        description: str,
        snapshot_id: Optional[str] = None,
        target: Optional[str] = None,
    ) -> RollbackPlan:
        """Create a rollback plan from a snapshot.

        Either snapshot_id or target must be provided. If target
        is given, uses the most recent snapshot for that target.

        Args:
            description: Why we're rolling back.
            snapshot_id: Specific snapshot to roll back to.
            target: Target to find the latest snapshot for.

        Returns:
            RollbackPlan with steps to execute.
        """
        # Find the snapshot
        snapshot: Optional[Snapshot] = None
        if snapshot_id:
            snapshot = self._snapshots.get_snapshot(snapshot_id)
        elif target:
            snapshot = self._snapshots.get_latest_for_target(target)

        if not snapshot:
            # No snapshot found — create empty plan with manual guidance
            plan = RollbackPlan(
                id=f"plan-{int(time.time())}",
                description=description,
            )
            plan.steps.append(RollbackStep(
                description="No snapshot available — manual intervention required",
                command="# No automatic rollback available",
                target=target or "unknown",
                snapshot_id="none",
            ))
            return plan

        # Build plan from snapshot
        steps: List[RollbackStep] = []

        if snapshot.snapshot_type == SnapshotType.COMPOSITE:
            # Composite: reverse-order sub-snapshots
            sub_ids = snapshot.metadata.get("sub_snapshots", [])
            for i, sub_id in enumerate(reversed(sub_ids)):
                sub = self._snapshots.get_snapshot(sub_id)
                if sub and sub.rollback_command:
                    steps.append(RollbackStep(
                        description=f"Restore {sub.target} from {sub.id}",
                        command=sub.rollback_command,
                        target=sub.target,
                        snapshot_id=sub.id,
                        order=i,
                    ))
        elif snapshot.rollback_command:
            # Single snapshot with rollback command
            steps.append(RollbackStep(
                description=f"Restore {snapshot.target} from snapshot {snapshot.id}",
                command=snapshot.rollback_command,
                target=snapshot.target,
                snapshot_id=snapshot.id,
                order=0,
            ))

        # Add verification step
        steps.append(RollbackStep(
            description="Verify rollback succeeded",
            command=f"# Verify {snapshot.target} is restored correctly",
            target=snapshot.target,
            snapshot_id=snapshot.id,
            order=len(steps),
        ))

        plan = RollbackPlan(
            id=f"plan-{int(time.time())}",
            description=description,
            steps=steps,
        )

        self._plans.append(plan)
        return plan

    async def execute_plan(
        self,
        plan: RollbackPlan,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute a rollback plan.

        Args:
            plan: The plan to execute.
            dry_run: If True, just log what would happen.

        Returns:
            Dict with execution results.
        """
        if dry_run:
            return {
                "dry_run": True,
                "plan": plan.preview(),
                "steps": plan.step_count,
            }

        results: List[Dict[str, Any]] = []
        all_success = True

        for step in sorted(plan.steps, key=lambda s: s.order):
            if step.command.startswith("#"):
                # Comment/manual step — skip
                step.executed = True
                step.success = True
                results.append({
                    "step": step.description,
                    "skipped": True,
                    "reason": "Manual/verification step",
                })
                continue

            logger.info(f"Rollback step: {step.description}")

            if self._executor:
                try:
                    output = await self._executor(step.command)
                    step.executed = True
                    step.success = True
                    results.append({
                        "step": step.description,
                        "success": True,
                        "output": output,
                    })
                except Exception as e:
                    step.executed = True
                    step.success = False
                    step.error = str(e)
                    all_success = False
                    results.append({
                        "step": step.description,
                        "success": False,
                        "error": str(e),
                    })
            else:
                # No executor — just mark as executed (simulated)
                step.executed = True
                step.success = True
                results.append({
                    "step": step.description,
                    "simulated": True,
                    "command": step.command,
                })

        plan.executed = True
        plan.executed_at = time.time()
        plan.partial = not all_success

        # Mark snapshots as used
        for step in plan.steps:
            snapshot = self._snapshots.get_snapshot(step.snapshot_id)
            if snapshot:
                snapshot.used_for_rollback = True

        return {
            "success": all_success,
            "steps_executed": sum(1 for r in results if not r.get("skipped")),
            "results": results,
            "plan_summary": plan.summary(),
        }

    def get_recent_plans(self, limit: int = 10) -> List[RollbackPlan]:
        """Get recent rollback plans."""
        return sorted(
            self._plans, key=lambda p: p.created_at, reverse=True
        )[:limit]

    def can_rollback(self, target: str) -> bool:
        """Check if a rollback is possible for a target.

        Args:
            target: The target to check.

        Returns:
            True if a snapshot exists for this target.
        """
        return self._snapshots.get_latest_for_target(target) is not None
