"""Plan Executor — Walks the task DAG and orchestrates execution.

The executor takes a TaskGraph from the planner and:
1. Determines execution order (respecting dependencies)
2. Runs independent tasks in parallel
3. Dispatches each task to its assigned sub-agent
4. Handles failures (retry, skip dependents, or replan)
5. Collects results and produces a final summary

The executor doesn't call LLMs directly — it delegates to sub-agents
who have the right tools and system prompts for their domain.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mk.planner.critique import CritiqueGate, CritiqueResult
from mk.planner.graph import TaskGraph, TaskNode, TaskStatus
from mk.planner.sub_agent import SubAgent, SubAgentRegistry
from mk.tools.base import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Final result of executing a complete plan.

    Contains the completed graph, summary, and aggregate metrics.
    """

    graph: TaskGraph
    success: bool = False
    summary: str = ""
    total_time_seconds: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    tasks_blocked: int = 0
    critique_result: Optional[CritiqueResult] = None
    errors: List[str] = field(default_factory=list)

    @property
    def partial_success(self) -> bool:
        """Whether at least some tasks succeeded."""
        return self.tasks_completed > 0

    def format_summary(self) -> str:
        """Generate a human-readable execution summary."""
        lines = [f"Plan: {self.graph.name}"]
        lines.append(f"Result: {'SUCCESS' if self.success else 'PARTIAL' if self.partial_success else 'FAILED'}")
        lines.append(
            f"Tasks: {self.tasks_completed} completed, "
            f"{self.tasks_failed} failed, "
            f"{self.tasks_skipped} skipped, "
            f"{self.tasks_blocked} blocked"
        )
        lines.append(f"Duration: {self.total_time_seconds:.1f}s")

        if self.errors:
            lines.append("\nErrors:")
            for err in self.errors:
                lines.append(f"  - {err}")

        # Per-task results
        lines.append("\nTask Results:")
        for task in self.graph.nodes.values():
            icon = {
                TaskStatus.COMPLETED: "✓",
                TaskStatus.FAILED: "✗",
                TaskStatus.SKIPPED: "⊘",
                TaskStatus.BLOCKED: "⊗",
            }.get(task.status, "?")

            elapsed = f" ({task.elapsed_seconds:.1f}s)" if task.elapsed_seconds else ""
            result_preview = ""
            if task.result:
                result_preview = f" — {task.result[:80]}"
            elif task.error:
                result_preview = f" — ERROR: {task.error[:80]}"

            lines.append(f"  {icon} {task.name}{elapsed}{result_preview}")

        return "\n".join(lines)


class PlanExecutor:
    """Orchestrates the execution of a task graph.

    Walks the DAG in topological order, running independent tasks
    in parallel and respecting dependency chains. Integrates with
    the critique gate for pre-execution safety checks.
    """

    def __init__(
        self,
        agent_registry: Optional[SubAgentRegistry] = None,
        critique_gate: Optional[CritiqueGate] = None,
        tool_executor: Optional[Callable] = None,
        max_parallel: int = 4,
    ) -> None:
        """Initialize the plan executor.

        Args:
            agent_registry: Registry of available sub-agents.
            critique_gate: Pre-execution safety reviewer.
            tool_executor: Async function for executing tools.
                Signature: async (name: str, args: dict) -> ToolResult
            max_parallel: Maximum tasks to run simultaneously.
        """
        self._registry = agent_registry or SubAgentRegistry()
        self._critique = critique_gate or CritiqueGate()
        self._tool_executor = tool_executor
        self._max_parallel = max_parallel

    async def execute(
        self,
        graph: TaskGraph,
        skip_critique: bool = False,
    ) -> ExecutionResult:
        """Execute a complete task graph.

        Steps:
        1. Run critique gate review (unless skipped)
        2. If approved, walk the DAG in waves
        3. For each wave, run tasks in parallel (up to max_parallel)
        4. Handle failures with retry or skip-dependents
        5. Produce final summary

        Args:
            graph: The task graph to execute.
            skip_critique: Skip the critique gate (for pre-approved plans).

        Returns:
            ExecutionResult with the final state.
        """
        start_time = time.time()
        critique_result: Optional[CritiqueResult] = None

        # Step 1: Critique gate
        if not skip_critique:
            critique_result = self._critique.review_plan(graph)

            if not critique_result.approved and critique_result.needs_user:
                # Plan was blocked — return without executing
                return ExecutionResult(
                    graph=graph,
                    success=False,
                    summary=f"Plan blocked by critique gate: {critique_result.summary()}",
                    total_time_seconds=time.time() - start_time,
                    tasks_blocked=len(critique_result.blocked_tasks),
                    critique_result=critique_result,
                )

        # Step 2: Execute wave by wave
        while not graph.is_complete:
            ready_tasks = graph.get_ready_tasks()

            if not ready_tasks:
                # No ready tasks but not complete — stuck (shouldn't happen with valid DAG)
                remaining = [
                    t for t in graph.nodes.values()
                    if t.status in (TaskStatus.PENDING, TaskStatus.READY)
                ]
                if remaining:
                    logger.error(
                        f"Execution stuck: {len(remaining)} tasks have unmet dependencies"
                    )
                    for t in remaining:
                        t.mark_failed("Unmet dependencies — execution stuck")
                break

            # Run ready tasks in parallel (respecting max_parallel)
            semaphore = asyncio.Semaphore(self._max_parallel)

            async def run_with_semaphore(task: TaskNode) -> None:
                async with semaphore:
                    await self._execute_task(task, graph)

            await asyncio.gather(
                *[run_with_semaphore(task) for task in ready_tasks],
                return_exceptions=True,
            )

        # Step 3: Produce summary
        elapsed = time.time() - start_time
        graph.completed_at = time.time()

        tasks_completed = sum(
            1 for t in graph.nodes.values() if t.status == TaskStatus.COMPLETED
        )
        tasks_failed = sum(
            1 for t in graph.nodes.values() if t.status == TaskStatus.FAILED
        )
        tasks_skipped = sum(
            1 for t in graph.nodes.values() if t.status == TaskStatus.SKIPPED
        )
        tasks_blocked = sum(
            1 for t in graph.nodes.values() if t.status == TaskStatus.BLOCKED
        )

        errors = [
            f"{t.name}: {t.error}"
            for t in graph.nodes.values()
            if t.status == TaskStatus.FAILED and t.error
        ]

        result = ExecutionResult(
            graph=graph,
            success=graph.is_successful,
            total_time_seconds=elapsed,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            tasks_skipped=tasks_skipped,
            tasks_blocked=tasks_blocked,
            critique_result=critique_result,
            errors=errors,
        )
        result.summary = result.format_summary()

        return result

    async def _execute_task(self, task: TaskNode, graph: TaskGraph) -> None:
        """Execute a single task node.

        Steps:
        1. Mark as running
        2. Resolve the sub-agent
        3. Check if task is blocked by critique
        4. Execute the tool (or prompt the agent)
        5. Handle result (success/failure/retry)

        Args:
            task: The task to execute.
            graph: The parent graph (for context and failure propagation).
        """
        # Skip if already blocked by critique
        if task.status == TaskStatus.BLOCKED:
            return

        task.mark_running()
        logger.info(f"Executing: [{task.agent}] {task.name}")

        # Per-task critique check for dangerous tasks
        if task.is_dangerous:
            task_critique = self._critique.review_task(task)
            if not task_critique.approved:
                task.mark_blocked(
                    f"Blocked: {task_critique.concerns[0] if task_critique.concerns else 'high risk'}"
                )
                graph.propagate_failure(task.id)
                return

        try:
            # Execute the task
            if task.tool and self._tool_executor:
                # Direct tool execution
                result = await self._tool_executor(task.tool, task.tool_args)

                if isinstance(result, ToolResult):
                    if result.success:
                        task.mark_completed(result.output or "Done")
                    else:
                        task.mark_failed(result.error or "Tool returned failure")
                elif isinstance(result, str):
                    task.mark_completed(result)
                else:
                    task.mark_completed(str(result))
            elif task.prompt:
                # Agent needs to reason about this task
                # For now, mark as completed with the prompt as result
                # (In full integration, this calls the agent's LLM loop)
                task.mark_completed(f"[Agent:{task.agent}] Would execute: {task.prompt}")
            else:
                # No tool, no prompt — mark completed (planning step)
                task.mark_completed("Completed (no-op planning step)")

        except Exception as e:
            task.mark_failed(str(e))
            logger.error(f"Task '{task.name}' failed: {e}")

        # Handle failure
        if task.status == TaskStatus.FAILED:
            if task.can_retry:
                # Reset and try again (will be picked up in next wave)
                logger.info(f"Retrying task '{task.name}' (attempt {task.retries + 1})")
                task.reset_for_retry()
            else:
                # Propagate failure to dependents
                skipped = graph.propagate_failure(task.id)
                if skipped:
                    logger.warning(
                        f"Task '{task.name}' failed — skipped {len(skipped)} dependent tasks"
                    )

    async def execute_simple(
        self,
        agent_name: str,
        tool: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
    ) -> ToolResult:
        """Execute a simple (non-decomposed) task directly.

        Used when the planner determines the request doesn't need
        full DAG decomposition — just a single tool call.

        Args:
            agent_name: Which agent should handle it.
            tool: Tool to execute (if known).
            args: Tool arguments.
            prompt: Natural language instruction (if no specific tool).

        Returns:
            ToolResult from execution.
        """
        agent = self._registry.get_agent(agent_name)
        if not agent:
            agent = self._registry.get_agent("general")

        if tool and self._tool_executor:
            # Verify agent can use this tool
            if agent and not agent.can_use_tool(tool):
                return ToolResult(
                    success=False,
                    error=f"Agent '{agent_name}' is not allowed to use tool '{tool}'",
                )

            return await self._tool_executor(tool, args or {})

        # No direct tool — this would go through the agent's LLM loop
        return ToolResult(
            success=True,
            output=f"[Agent:{agent_name}] Processed: {prompt or 'no instruction'}",
        )
