"""Task Graph — DAG-based task decomposition structure.

A TaskGraph represents a complex user request broken into atomic
sub-tasks with explicit dependencies. Tasks that don't depend on
each other can run in parallel; tasks with dependencies wait.

Example:
    "Set up a new media server" becomes:
    
    ┌─────────────────┐     ┌──────────────────┐
    │ check_storage   │     │ pull_image       │
    └────────┬────────┘     └────────┬─────────┘
             │                       │
             ▼                       │
    ┌─────────────────┐              │
    │ create_dataset  │              │
    └────────┬────────┘              │
             │                       │
             ▼                       ▼
    ┌───────────────────────────────────────┐
    │          deploy_container             │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │         configure_proxy              │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │          health_check                │
    └───────────────────────────────────────┘
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Lifecycle status of a task node."""

    PENDING = "pending"          # Waiting for dependencies
    READY = "ready"              # Dependencies met, can execute
    RUNNING = "running"          # Currently executing
    COMPLETED = "completed"      # Finished successfully
    FAILED = "failed"            # Execution failed
    SKIPPED = "skipped"          # Skipped (dependency failed, or critique blocked)
    BLOCKED = "blocked"          # Blocked by critique gate
    CANCELLED = "cancelled"      # User or system cancelled


class TaskNode(BaseModel):
    """A single task in the execution graph.

    Each node represents one atomic action that a sub-agent can execute.
    Nodes track their own state, results, and execution metadata.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = Field(description="Human-readable task name")
    description: str = Field(default="", description="What this task does")

    # Execution spec
    agent: str = Field(
        default="general",
        description="Which sub-agent should handle this (e.g., 'devops', 'media')",
    )
    tool: Optional[str] = Field(
        default=None,
        description="Specific tool to use (if known at planning time)",
    )
    tool_args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments for the tool (if known at planning time)",
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Natural language instruction for the sub-agent",
    )

    # Dependencies
    depends_on: List[str] = Field(
        default_factory=list,
        description="IDs of tasks that must complete before this one",
    )

    # State
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    result: Optional[str] = Field(default=None, description="Execution result")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    retries: int = Field(default=0, description="Number of retry attempts")
    max_retries: int = Field(default=2, description="Maximum retries on failure")

    # Risk assessment
    is_dangerous: bool = Field(
        default=False,
        description="Whether this task modifies state irreversibly",
    )
    risk_description: Optional[str] = Field(
        default=None,
        description="What could go wrong",
    )
    rollback_hint: Optional[str] = Field(
        default=None,
        description="How to undo this if it goes wrong",
    )

    # Timing
    started_at: Optional[float] = Field(default=None)
    completed_at: Optional[float] = Field(default=None)

    @property
    def elapsed_seconds(self) -> Optional[float]:
        """Time taken to execute (None if not started/finished)."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return None

    @property
    def can_retry(self) -> bool:
        """Whether this task can be retried."""
        return self.status == TaskStatus.FAILED and self.retries < self.max_retries

    def mark_running(self) -> None:
        """Transition to running state."""
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self, result: str) -> None:
        """Transition to completed state."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()

    def mark_failed(self, error: str) -> None:
        """Transition to failed state."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = time.time()
        self.retries += 1

    def mark_skipped(self, reason: str = "") -> None:
        """Skip this task."""
        self.status = TaskStatus.SKIPPED
        self.result = reason or "Skipped due to dependency failure"
        self.completed_at = time.time()

    def mark_blocked(self, reason: str) -> None:
        """Block this task (critique gate denied it)."""
        self.status = TaskStatus.BLOCKED
        self.error = reason
        self.completed_at = time.time()

    def reset_blocked(self) -> None:
        """Reset a blocked task back to pending (user override).

        Used when the user explicitly confirms a dangerous action
        that was blocked by the critique gate.
        """
        if self.status == TaskStatus.BLOCKED:
            self.status = TaskStatus.PENDING
            self.error = None
            self.completed_at = None

    def reset_for_retry(self) -> None:
        """Reset state for a retry attempt."""
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.started_at = None
        self.completed_at = None


class TaskEdge(BaseModel):
    """An explicit dependency edge between two tasks."""

    source: str = Field(description="ID of the prerequisite task")
    target: str = Field(description="ID of the dependent task")
    data_key: Optional[str] = Field(
        default=None,
        description="If set, pass source result to target under this key",
    )


class TaskGraph(BaseModel):
    """Directed Acyclic Graph of tasks with dependency tracking.

    The graph is the central data structure for plan execution.
    It tracks all tasks, their relationships, and provides methods
    for determining execution order and parallelism opportunities.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = Field(default="", description="Plan name / user request summary")
    original_request: str = Field(default="", description="The original user input")

    # Structure
    nodes: Dict[str, TaskNode] = Field(default_factory=dict)
    edges: List[TaskEdge] = Field(default_factory=list)

    # Metadata
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = Field(default=None)

    def add_task(self, task: TaskNode) -> TaskNode:
        """Add a task to the graph.

        Args:
            task: The TaskNode to add.

        Returns:
            The added task.

        Raises:
            ValueError: If a task with the same ID already exists.
        """
        if task.id in self.nodes:
            raise ValueError(f"Task with ID '{task.id}' already exists")
        self.nodes[task.id] = task

        # Add edges for declared dependencies
        for dep_id in task.depends_on:
            self.edges.append(TaskEdge(source=dep_id, target=task.id))

        return task

    def add_dependency(
        self, from_id: str, to_id: str, data_key: Optional[str] = None
    ) -> None:
        """Add a dependency edge: to_id depends on from_id.

        Args:
            from_id: Prerequisite task ID.
            to_id: Dependent task ID.
            data_key: If set, pass from's result to to under this key.

        Raises:
            ValueError: If either task doesn't exist.
        """
        if from_id not in self.nodes:
            raise ValueError(f"Task '{from_id}' not found")
        if to_id not in self.nodes:
            raise ValueError(f"Task '{to_id}' not found")

        # Check for cycles
        if self._would_create_cycle(from_id, to_id):
            raise ValueError(
                f"Adding edge {from_id} -> {to_id} would create a cycle"
            )

        self.edges.append(TaskEdge(source=from_id, target=to_id, data_key=data_key))
        if from_id not in self.nodes[to_id].depends_on:
            self.nodes[to_id].depends_on.append(from_id)

    def get_ready_tasks(self) -> List[TaskNode]:
        """Get all tasks whose dependencies are met and can be executed.

        A task is ready when:
        - It's in PENDING status
        - All tasks in its depends_on list are COMPLETED
        - All dependency IDs actually exist in the graph

        Returns:
            List of tasks ready for execution (can run in parallel).
        """
        ready: List[TaskNode] = []

        for task in self.nodes.values():
            if task.status != TaskStatus.PENDING:
                continue

            # Check all dependencies exist and are completed
            deps_met = True
            for dep_id in task.depends_on:
                if dep_id not in self.nodes:
                    # Missing dependency — treat as unmet (fail-safe)
                    deps_met = False
                    break
                if self.nodes[dep_id].status != TaskStatus.COMPLETED:
                    deps_met = False
                    break

            if deps_met:
                task.status = TaskStatus.READY
                ready.append(task)

        return ready

    def get_task(self, task_id: str) -> Optional[TaskNode]:
        """Get a task by ID."""
        return self.nodes.get(task_id)

    def get_dependents(self, task_id: str) -> List[TaskNode]:
        """Get all tasks that depend on the given task.

        Args:
            task_id: The task to find dependents for.

        Returns:
            List of tasks that depend on task_id.
        """
        dependents: List[TaskNode] = []
        for edge in self.edges:
            if edge.source == task_id:
                dependent = self.nodes.get(edge.target)
                if dependent:
                    dependents.append(dependent)
        return dependents

    def propagate_failure(self, failed_task_id: str) -> List[str]:
        """Skip all tasks that depend (directly or transitively) on a failed task.

        Args:
            failed_task_id: The task that failed.

        Returns:
            List of task IDs that were skipped.
        """
        skipped: List[str] = []
        to_process = [failed_task_id]
        visited: Set[str] = set()

        while to_process:
            current = to_process.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for dependent in self.get_dependents(current):
                if dependent.status in (TaskStatus.PENDING, TaskStatus.READY):
                    dependent.mark_skipped(
                        f"Skipped: dependency '{current}' failed"
                    )
                    skipped.append(dependent.id)
                    to_process.append(dependent.id)

        return skipped

    @property
    def is_complete(self) -> bool:
        """Whether all tasks have reached a terminal state."""
        terminal = {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.SKIPPED,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }
        return all(t.status in terminal for t in self.nodes.values())

    @property
    def is_successful(self) -> bool:
        """Whether all tasks completed successfully."""
        return all(
            t.status == TaskStatus.COMPLETED for t in self.nodes.values()
        )

    @property
    def progress(self) -> Dict[str, int]:
        """Get a count of tasks in each status."""
        counts: Dict[str, int] = {}
        for task in self.nodes.values():
            status = task.status.value
            counts[status] = counts.get(status, 0) + 1
        return counts

    @property
    def task_count(self) -> int:
        """Total number of tasks."""
        return len(self.nodes)

    @property
    def dangerous_tasks(self) -> List[TaskNode]:
        """All tasks marked as dangerous."""
        return [t for t in self.nodes.values() if t.is_dangerous]

    def execution_order(self) -> List[List[str]]:
        """Get the topological execution order grouped by parallel batches.

        Returns a list of "waves" — each wave is a list of task IDs
        that can execute in parallel. Waves execute sequentially.

        Tasks with invalid dependencies (referencing non-existent nodes)
        are excluded from the ordering.

        Returns:
            List of parallel batches, e.g., [["a","b"], ["c"], ["d","e"]]
        """
        # Kahn's algorithm with batching
        # Only consider edges where both source and target exist
        valid_edges = [
            e for e in self.edges
            if e.source in self.nodes and e.target in self.nodes
        ]

        # Exclude tasks with invalid (unresolvable) dependencies
        valid_nodes = set()
        for tid, task in self.nodes.items():
            has_invalid_dep = any(
                dep_id not in self.nodes for dep_id in task.depends_on
            )
            if not has_invalid_dep:
                valid_nodes.add(tid)

        in_degree: Dict[str, int] = {tid: 0 for tid in valid_nodes}
        for edge in valid_edges:
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        waves: List[List[str]] = []
        remaining = set(valid_nodes)

        while remaining:
            # Find all nodes with in-degree 0 (among remaining)
            wave = [
                tid for tid in remaining
                if in_degree.get(tid, 0) == 0
            ]

            if not wave:
                # Cycle detected (shouldn't happen if we validate)
                break

            waves.append(wave)

            # Remove this wave and update in-degrees
            for tid in wave:
                remaining.discard(tid)
                for edge in valid_edges:
                    if edge.source == tid and edge.target in remaining:
                        in_degree[edge.target] -= 1

        return waves

    def summary(self) -> str:
        """Get a human-readable summary of the plan.

        Returns:
            Formatted string showing the plan structure.
        """
        lines = [f"Plan: {self.name or self.original_request}"]
        lines.append(f"Tasks: {self.task_count} | Progress: {self.progress}")
        lines.append("")

        waves = self.execution_order()
        for i, wave in enumerate(waves):
            lines.append(f"  Wave {i + 1}:")
            for tid in wave:
                task = self.nodes[tid]
                status_icon = {
                    TaskStatus.PENDING: "○",
                    TaskStatus.READY: "◎",
                    TaskStatus.RUNNING: "●",
                    TaskStatus.COMPLETED: "✓",
                    TaskStatus.FAILED: "✗",
                    TaskStatus.SKIPPED: "⊘",
                    TaskStatus.BLOCKED: "⊗",
                    TaskStatus.CANCELLED: "⊖",
                }.get(task.status, "?")

                danger = " ⚠️" if task.is_dangerous else ""
                lines.append(
                    f"    {status_icon} [{task.agent}] {task.name}{danger}"
                )

        return "\n".join(lines)

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """Check if adding an edge from_id -> to_id would create a cycle.

        Uses DFS from to_id to see if from_id is reachable.
        """
        visited: Set[str] = set()
        stack = [to_id]

        while stack:
            current = stack.pop()
            if current == from_id:
                return True
            if current in visited:
                continue
            visited.add(current)

            # Follow outgoing edges
            for edge in self.edges:
                if edge.source == current:
                    stack.append(edge.target)

        return False
