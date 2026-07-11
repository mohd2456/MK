"""Task Planner — Decomposes complex requests into task graphs.

The planner is the brain's planning layer. Given a user request, it:
1. Determines if the request is simple (single tool call) or complex
2. For complex requests: decomposes into a DAG of sub-tasks
3. Assigns each sub-task to the appropriate specialist sub-agent
4. Identifies dependencies and parallelism opportunities
5. Marks dangerous tasks for critique gate review

The planner uses TWO strategies:
- Rule-based: For common patterns (restart X, setup Y, etc.)
- LLM-based: For novel/complex requests that need reasoning

Rule-based planning is free and instant. LLM-based planning costs tokens
but handles arbitrary complexity.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mk.planner.graph import TaskGraph, TaskNode
from mk.planner.sub_agent import SubAgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class PlanResult:
    """Result of the planning phase.

    Contains the task graph (if decomposed) or a simple task (if trivial).
    The executor checks is_simple to decide whether to use the full DAG
    execution or just run a single tool call.
    """

    graph: Optional[TaskGraph] = None
    is_simple: bool = False
    simple_agent: str = "general"
    simple_tool: Optional[str] = None
    simple_args: Dict[str, Any] = field(default_factory=dict)
    simple_prompt: Optional[str] = None
    planning_method: str = "none"  # "rules", "llm", "passthrough"
    reasoning: str = ""  # Why the planner made this decision


class TaskPlanner:
    """Decomposes complex requests into executable task graphs.

    Two planning modes:
    1. Rule-based: Pattern matching for common homelab operations
    2. LLM-based: For novel requests that need reasoning to decompose

    The planner is conservative — if unsure, it creates a simple
    passthrough plan rather than a bad decomposition.
    """

    def __init__(
        self,
        agent_registry: Optional[SubAgentRegistry] = None,
        llm_planner: Optional[Callable] = None,
    ) -> None:
        """Initialize the task planner.

        Args:
            agent_registry: Registry of available sub-agents.
            llm_planner: Optional async function for LLM-based planning.
                Signature: async (request: str) -> TaskGraph
        """
        self._registry = agent_registry or SubAgentRegistry()
        self._llm_planner = llm_planner
        self._plan_templates = self._build_templates()

    def plan(self, user_request: str) -> PlanResult:
        """Create an execution plan for a user request.

        Decision flow:
        1. Is it trivially simple? → passthrough (no planning needed)
        2. Does it match a known template? → rule-based plan
        3. Is it complex? → LLM-based plan (or passthrough if no LLM)

        Args:
            user_request: The user's natural language request.

        Returns:
            PlanResult with either a TaskGraph or simple execution spec.
        """
        text = user_request.strip()

        # Trivially simple: single-word commands, greetings, etc.
        if self._is_trivial(text):
            return PlanResult(
                is_simple=True,
                simple_agent="general",
                simple_prompt=text,
                planning_method="passthrough",
                reasoning="Trivial request — no decomposition needed",
            )

        # Try rule-based templates
        template_result = self._match_template(text)
        if template_result:
            return template_result

        # Complex request — if we have an LLM, use it for planning
        # Otherwise, passthrough to the general agent
        return PlanResult(
            is_simple=True,
            simple_agent="general",
            simple_prompt=text,
            planning_method="passthrough",
            reasoning="No template match — passing through to general agent",
        )

    async def plan_with_llm(self, user_request: str) -> PlanResult:
        """Create a plan using LLM reasoning (async).

        Only called when rule-based planning doesn't apply and an
        LLM planner is configured.

        Args:
            user_request: The user's request.

        Returns:
            PlanResult with a TaskGraph from LLM decomposition.
        """
        if not self._llm_planner:
            return self.plan(user_request)

        try:
            graph = await self._llm_planner(user_request)
            if graph and graph.task_count > 0:
                return PlanResult(
                    graph=graph,
                    is_simple=False,
                    planning_method="llm",
                    reasoning="LLM decomposed request into task graph",
                )
        except Exception as e:
            logger.warning(f"LLM planning failed: {e}, falling back to passthrough")

        # Fallback
        return self.plan(user_request)

    def _is_trivial(self, text: str) -> bool:
        """Check if a request is too simple to need planning."""
        # Single words or very short
        if len(text.split()) <= 2:
            return True

        # Greetings and meta-commands
        trivial_starts = (
            "hi",
            "hey",
            "hello",
            "thanks",
            "help",
            "status",
            "bye",
            "quit",
            "exit",
            "version",
            "who",
        )
        first_word = text.split()[0].lower().rstrip("?!.")
        return first_word in trivial_starts

    def _match_template(self, text: str) -> Optional[PlanResult]:
        """Try to match the request against known plan templates.

        Templates are pre-built task graphs for common operations.
        Much faster and more predictable than LLM planning.
        """
        text_lower = text.lower()

        for template in self._plan_templates:
            match = template["pattern"].search(text_lower)
            if match:
                builder = template["builder"]
                return builder(match, text)

        return None

    def _build_templates(self) -> List[Dict[str, Any]]:
        """Build the rule-based plan templates."""
        return [
            # "Set up X service/container"
            {
                "pattern": re.compile(
                    r"(?:set\s*up|deploy|install|create)\s+(?:a\s+)?(?:new\s+)?(.+?)(?:\s+(?:service|container|server))?$"
                ),
                "builder": self._plan_deploy_service,
            },
            # "Move/transfer X to Y"
            {
                "pattern": re.compile(
                    r"(?:move|transfer|copy|migrate)\s+(.+?)\s+(?:to|into|onto)\s+(.+)"
                ),
                "builder": self._plan_transfer,
            },
            # "Update/upgrade all/everything"
            {
                "pattern": re.compile(r"(?:update|upgrade)\s+(?:all|everything|containers|system)"),
                "builder": self._plan_update_all,
            },
            # "Backup X" or "run backup"
            {
                "pattern": re.compile(r"(?:backup|back\s*up|snapshot)\s+(.+)"),
                "builder": self._plan_backup,
            },
            # "Rip/process disc"
            {
                "pattern": re.compile(
                    r"(?:rip|process|encode)\s+(?:the\s+)?(?:disc|disk|blu-?ray|dvd|movie)\s*(.*)"
                ),
                "builder": self._plan_disc_rip,
            },
        ]

    def _plan_deploy_service(self, match: re.Match, original: str) -> PlanResult:
        """Build a plan for deploying a new service."""
        service_name = match.group(1).strip()

        graph = TaskGraph(
            name=f"Deploy {service_name}",
            original_request=original,
        )

        # Task 1: Check resources (parallel with 2)
        t1 = TaskNode(
            name="Check available resources",
            description=f"Verify disk space and memory for {service_name}",
            agent="devops",
            tool="system_monitor",
            tool_args={"action": "get_system_stats"},
        )

        # Task 2: Pull/prepare image (parallel with 1)
        t2 = TaskNode(
            name=f"Pull container image for {service_name}",
            description=f"Pull the Docker image for {service_name}",
            agent="devops",
            tool="docker",
            tool_args={"action": "pull", "image": service_name},
        )

        # Task 3: Create storage (depends on 1)
        t3 = TaskNode(
            name=f"Create storage for {service_name}",
            description=f"Create data directory or ZFS dataset for {service_name}",
            agent="devops",
            depends_on=[t1.id],
        )

        # Task 4: Deploy container (depends on 2, 3)
        t4 = TaskNode(
            name=f"Deploy {service_name} container",
            description=f"Start the {service_name} container with proper config",
            agent="devops",
            tool="docker",
            tool_args={"action": "deploy_compose"},
            depends_on=[t2.id, t3.id],
            is_dangerous=True,
            risk_description=f"Creates new container for {service_name}",
            rollback_hint=f"docker stop {service_name} && docker rm {service_name}",
        )

        # Task 5: Health check (depends on 4)
        t5 = TaskNode(
            name=f"Verify {service_name} is healthy",
            description=f"Check that {service_name} started correctly and is responding",
            agent="devops",
            tool="system_monitor",
            tool_args={"action": "check_health", "service_name": service_name},
            depends_on=[t4.id],
        )

        for task in [t1, t2, t3, t4, t5]:
            graph.add_task(task)

        return PlanResult(
            graph=graph,
            is_simple=False,
            planning_method="rules",
            reasoning=f"Matched deploy template for '{service_name}'",
        )

    def _plan_transfer(self, match: re.Match, original: str) -> PlanResult:
        """Build a plan for transferring files between machines."""
        source = match.group(1).strip()
        destination = match.group(2).strip()

        graph = TaskGraph(
            name=f"Transfer {source} → {destination}",
            original_request=original,
        )

        # Task 1: Verify source exists
        t1 = TaskNode(
            name=f"Verify source: {source}",
            description=f"Check that {source} exists and is accessible",
            agent="devops",
            tool="ssh",
            tool_args={"action": "run_command", "command": f"ls -la {source}"},
        )

        # Task 2: Check destination space
        t2 = TaskNode(
            name="Check space at destination",
            description=f"Verify {destination} has enough space",
            agent="devops",
            tool="ssh",
            tool_args={"action": "run_command", "command": f"df -h {destination}"},
        )

        # Task 3: Transfer (depends on 1, 2)
        t3 = TaskNode(
            name="Transfer via rsync",
            description=f"rsync {source} → {destination} over private network",
            agent="devops",
            tool="ssh",
            tool_args={
                "action": "run_command",
                "command": f"rsync -avz --progress {source} {destination}",
            },
            depends_on=[t1.id, t2.id],
        )

        # Task 4: Verify transfer (depends on 3)
        t4 = TaskNode(
            name="Verify transfer integrity",
            description="Compare file checksums between source and destination",
            agent="devops",
            depends_on=[t3.id],
        )

        for task in [t1, t2, t3, t4]:
            graph.add_task(task)

        return PlanResult(
            graph=graph,
            is_simple=False,
            planning_method="rules",
            reasoning=f"Matched transfer template: {source} → {destination}",
        )

    def _plan_update_all(self, match: re.Match, original: str) -> PlanResult:
        """Build a plan for updating all containers/system."""
        graph = TaskGraph(
            name="Update all containers",
            original_request=original,
        )

        # Task 1: Create pre-update snapshot
        t1 = TaskNode(
            name="Create pre-update snapshot",
            description="Snapshot current state before updating",
            agent="backup",
            is_dangerous=False,
        )

        # Task 2: Pull all new images (depends on 1)
        t2 = TaskNode(
            name="Pull latest container images",
            description="docker compose pull for all services",
            agent="devops",
            tool="ssh",
            tool_args={
                "action": "run_command",
                "command": "cd /opt/docker && docker compose pull",
            },
            depends_on=[t1.id],
        )

        # Task 3: Recreate containers (depends on 2)
        t3 = TaskNode(
            name="Recreate containers with new images",
            description="docker compose up -d (recreates changed containers)",
            agent="devops",
            tool="ssh",
            tool_args={
                "action": "run_command",
                "command": "cd /opt/docker && docker compose up -d",
            },
            depends_on=[t2.id],
            is_dangerous=True,
            risk_description="Restarts all services — brief downtime",
            rollback_hint="Restore from pre-update snapshot",
        )

        # Task 4: Health check all (depends on 3)
        t4 = TaskNode(
            name="Verify all services healthy",
            description="Check each container is running and responding",
            agent="devops",
            tool="system_monitor",
            tool_args={"action": "check_health"},
            depends_on=[t3.id],
        )

        # Task 5: Clean old images (depends on 4)
        t5 = TaskNode(
            name="Clean up old images",
            description="Remove unused Docker images to free disk space",
            agent="devops",
            tool="ssh",
            tool_args={
                "action": "run_command",
                "command": "docker image prune -f",
            },
            depends_on=[t4.id],
        )

        for task in [t1, t2, t3, t4, t5]:
            graph.add_task(task)

        return PlanResult(
            graph=graph,
            is_simple=False,
            planning_method="rules",
            reasoning="Matched update-all template",
        )

    def _plan_backup(self, match: re.Match, original: str) -> PlanResult:
        """Build a plan for running a backup."""
        target = match.group(1).strip()

        graph = TaskGraph(
            name=f"Backup {target}",
            original_request=original,
        )

        t1 = TaskNode(
            name=f"Create ZFS snapshot of {target}",
            description=f"zfs snapshot for {target}",
            agent="backup",
            tool="ssh",
            tool_args={
                "action": "run_command",
                "command": f"zfs snapshot tank/{target}@manual-$(date +%Y%m%d_%H%M)",
            },
        )

        t2 = TaskNode(
            name="Verify backup",
            description="Verify the new snapshot is valid",
            agent="backup",
            tool="backup-verifier.verify_latest",
            tool_args={"pool": f"tank/{target}", "sample_count": 3},
            depends_on=[t1.id],
        )

        for task in [t1, t2]:
            graph.add_task(task)

        return PlanResult(
            graph=graph,
            is_simple=False,
            planning_method="rules",
            reasoning=f"Matched backup template for '{target}'",
        )

    def _plan_disc_rip(self, match: re.Match, original: str) -> PlanResult:
        """Build a plan for ripping and processing a disc."""
        title_hint = match.group(1).strip() if match.group(1) else "unknown"

        graph = TaskGraph(
            name=f"Rip and process disc: {title_hint}",
            original_request=original,
        )

        # Task 1: Check disc drive
        t1 = TaskNode(
            name="Check disc drive status",
            description="Verify a disc is inserted and readable",
            agent="media",
        )

        # Task 2: Rip disc (depends on 1)
        t2 = TaskNode(
            name="Rip disc to MKV",
            description="Use MakeMKV to rip the disc to /data/rips/",
            agent="media",
            depends_on=[t1.id],
        )

        # Task 3: Identify title (depends on 2)
        t3 = TaskNode(
            name="Identify movie/show title",
            description="Match the rip against TMDb/TVDB for proper naming",
            agent="media",
            depends_on=[t2.id],
        )

        # Task 4: Rename and organize (depends on 3)
        t4 = TaskNode(
            name="Rename and organize file",
            description="Move to Plex library with proper naming convention",
            agent="media",
            tool="files",
            depends_on=[t3.id],
        )

        # Task 5: Trigger Plex scan (depends on 4)
        t5 = TaskNode(
            name="Trigger Plex library scan",
            description="Tell Plex to scan for new content",
            agent="media",
            depends_on=[t4.id],
        )

        # Task 6: Clean up raw rip (depends on 5)
        t6 = TaskNode(
            name="Clean up raw rip",
            description="Delete the raw rip from /data/rips/ to free space",
            agent="media",
            depends_on=[t5.id],
            is_dangerous=True,
            risk_description="Deletes raw rip file (large, but already processed)",
            rollback_hint="File already in Plex library — re-rip if needed",
        )

        for task in [t1, t2, t3, t4, t5, t6]:
            graph.add_task(task)

        return PlanResult(
            graph=graph,
            is_simple=False,
            planning_method="rules",
            reasoning=f"Matched disc-rip template for '{title_hint}'",
        )
