"""Sub-Agent system — Specialist agents with focused capabilities.

Instead of one generalist agent trying to handle everything, MK delegates
to specialist sub-agents. Each sub-agent:
- Has a focused system prompt (knows its domain deeply)
- Sees only the tools relevant to its domain
- Has stricter safety boundaries (DevOps agent can't touch media files)
- Can be swapped/upgraded independently

Built-in specialists:
- DevOps: containers, services, networking, SSH, system management
- Media: Plex, Sonarr, Radarr, disc ripping, file organization
- Network: DNS, firewall, routing, VPN, certificates
- General: Fallback for anything that doesn't fit a specialist

Sub-agents are NOT full LLM loops — they're execution contexts.
The TaskPlanner decides what each agent should do; the agent just does it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from mk.tools.base import ToolResult

logger = logging.getLogger(__name__)


class AgentCapability(str, Enum):
    """Capabilities that sub-agents can declare.

    Used for routing — the planner matches task requirements
    to agent capabilities to pick the best agent for each task.
    """

    CONTAINERS = "containers"
    SERVICES = "services"
    STORAGE = "storage"
    NETWORKING = "networking"
    SSH = "ssh"
    MEDIA = "media"
    BACKUP = "backup"
    MONITORING = "monitoring"
    FILES = "files"
    SECURITY = "security"
    DNS = "dns"
    CERTIFICATES = "certificates"
    LLM_REASONING = "llm_reasoning"
    USER_INTERACTION = "user_interaction"


@dataclass
class SubAgent:
    """A specialist sub-agent with focused domain knowledge.

    Sub-agents are execution contexts — they know what tools they can use,
    what their system prompt is, and how to execute tasks in their domain.
    They don't run their own reasoning loops; the PlanExecutor tells them
    exactly what to do.

    Attributes:
        name: Unique agent identifier (e.g., "devops", "media").
        description: What this agent specializes in.
        capabilities: What types of tasks this agent can handle.
        allowed_tools: Tool names this agent can use (qualified or unqualified).
        system_prompt: Domain-specific system prompt for LLM calls.
        max_iterations: Max reasoning steps if this agent does get an LLM loop.
    """

    name: str
    description: str
    capabilities: Set[AgentCapability] = field(default_factory=set)
    allowed_tools: Set[str] = field(default_factory=set)
    system_prompt: str = ""
    max_iterations: int = 5
    priority: int = 0  # Higher = preferred when multiple agents match

    def can_handle(self, required_capabilities: Set[AgentCapability]) -> bool:
        """Check if this agent has all the required capabilities.

        Args:
            required_capabilities: Capabilities needed for the task.

        Returns:
            True if this agent covers all requirements.
        """
        return required_capabilities.issubset(self.capabilities)

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if this agent is allowed to use a specific tool.

        Args:
            tool_name: The tool to check (qualified or unqualified).

        Returns:
            True if the tool is in the agent's allowed set.
        """
        if not self.allowed_tools:
            return True  # Empty = no restrictions (general agent)

        # Check exact match
        if tool_name in self.allowed_tools:
            return True

        # Check unqualified match (e.g., "docker" matches "docker.restart")
        base_name = tool_name.split(".")[0]
        return base_name in self.allowed_tools

    @property
    def capability_names(self) -> List[str]:
        """Get capability names as strings."""
        return [c.value for c in self.capabilities]


@dataclass
class SubAgentRegistry:
    """Registry of all available sub-agents.

    Provides lookup by name, capability matching, and tool routing.
    Pre-registers the built-in specialist agents on initialization.
    """

    _agents: Dict[str, SubAgent] = field(default_factory=dict)
    _initialized: bool = False

    def __post_init__(self) -> None:
        """Register built-in agents."""
        if not self._initialized:
            self._register_builtins()
            self._initialized = True

    def _register_builtins(self) -> None:
        """Register the built-in specialist sub-agents."""

        # DevOps Agent — containers, services, system management
        self.register(SubAgent(
            name="devops",
            description=(
                "Infrastructure specialist. Manages Docker containers, "
                "systemd services, system packages, and server health."
            ),
            capabilities={
                AgentCapability.CONTAINERS,
                AgentCapability.SERVICES,
                AgentCapability.STORAGE,
                AgentCapability.SSH,
                AgentCapability.MONITORING,
            },
            allowed_tools={
                "docker", "ssh", "system_monitor", "files",
                "backup-verifier",  # Plugin tools too
            },
            system_prompt=(
                "You are MK's DevOps specialist. You manage Docker containers, "
                "systemd services, ZFS storage, and server infrastructure. "
                "You are precise, careful, and always verify before destructive actions. "
                "Prefer `docker compose` over raw `docker run`. "
                "Always check service health after changes."
            ),
            priority=10,
        ))

        # Media Agent — Plex, Sonarr, Radarr, file organization
        self.register(SubAgent(
            name="media",
            description=(
                "Media management specialist. Handles Plex, Sonarr, Radarr, "
                "disc ripping, file naming, and media library organization."
            ),
            capabilities={
                AgentCapability.MEDIA,
                AgentCapability.FILES,
            },
            allowed_tools={
                "media", "files", "ssh",
            },
            system_prompt=(
                "You are MK's Media specialist. You manage the Plex media server, "
                "Sonarr (TV), Radarr (movies), and disc ripping workflows. "
                "You know Plex naming conventions perfectly. "
                "Always organize files as: Movies → 'Title (Year)/Title (Year).ext' "
                "and TV → 'Show/Season XX/Show - SXXEXX - Title.ext'. "
                "After any file move, trigger a Plex library scan."
            ),
            priority=10,
        ))

        # Network Agent — DNS, firewall, certificates, routing
        self.register(SubAgent(
            name="network",
            description=(
                "Network specialist. Manages DNS records, firewall rules, "
                "reverse proxies, VPN, and TLS certificates."
            ),
            capabilities={
                AgentCapability.NETWORKING,
                AgentCapability.DNS,
                AgentCapability.CERTIFICATES,
                AgentCapability.SECURITY,
            },
            allowed_tools={
                "ssh", "files",
            },
            system_prompt=(
                "You are MK's Network specialist. You manage DNS, firewall rules, "
                "reverse proxy (Traefik/Nginx), VPN (WireGuard), and TLS certificates. "
                "Always use the private network for inter-machine traffic. "
                "Never expose services to 0.0.0.0 without explicit confirmation. "
                "Prefer Let's Encrypt for certificates."
            ),
            priority=10,
        ))

        # Backup Agent — backups, snapshots, disaster recovery
        self.register(SubAgent(
            name="backup",
            description=(
                "Backup and recovery specialist. Manages ZFS snapshots, "
                "restic backups, verification, and disaster recovery."
            ),
            capabilities={
                AgentCapability.BACKUP,
                AgentCapability.STORAGE,
            },
            allowed_tools={
                "ssh", "files", "backup-verifier",
            },
            system_prompt=(
                "You are MK's Backup specialist. You manage ZFS snapshots, "
                "restic backups, and disaster recovery. "
                "Always verify backups after creation. "
                "Keep at least 7 daily, 4 weekly, and 12 monthly snapshots. "
                "Test restores regularly."
            ),
            priority=8,
        ))

        # General Agent — fallback for everything else
        self.register(SubAgent(
            name="general",
            description=(
                "General-purpose agent. Handles tasks that don't fit "
                "a specialist, creative requests, and user interaction."
            ),
            capabilities={
                AgentCapability.LLM_REASONING,
                AgentCapability.USER_INTERACTION,
                AgentCapability.FILES,
            },
            allowed_tools=set(),  # Empty = can use everything
            system_prompt=(
                "You are MK, a personal AI operating system. "
                "Handle this task directly — be concise and actionable."
            ),
            priority=0,  # Lowest priority — only used if no specialist matches
        ))

    def register(self, agent: SubAgent) -> None:
        """Register a sub-agent.

        Args:
            agent: The SubAgent to register.
        """
        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Optional[SubAgent]:
        """Get an agent by name.

        Args:
            name: Agent name.

        Returns:
            SubAgent or None.
        """
        return self._agents.get(name)

    def find_agent_for_task(
        self,
        required_capabilities: Optional[Set[AgentCapability]] = None,
        tool_name: Optional[str] = None,
        agent_hint: Optional[str] = None,
    ) -> SubAgent:
        """Find the best agent for a task.

        Selection logic:
        1. If agent_hint is given and valid, use it
        2. Find agents that have all required capabilities
        3. Among matches, prefer higher priority
        4. Fall back to the general agent

        Args:
            required_capabilities: Capabilities the task needs.
            tool_name: Tool the task will use (for filtering).
            agent_hint: Explicit agent name (from planner).

        Returns:
            The best matching SubAgent.
        """
        # Direct hint
        if agent_hint and agent_hint in self._agents:
            return self._agents[agent_hint]

        # Capability matching
        candidates: List[SubAgent] = []
        required = required_capabilities or set()

        for agent in self._agents.values():
            if agent.name == "general":
                continue  # Save general as fallback

            if required and not agent.can_handle(required):
                continue

            if tool_name and not agent.can_use_tool(tool_name):
                continue

            candidates.append(agent)

        # Sort by priority (highest first)
        candidates.sort(key=lambda a: a.priority, reverse=True)

        if candidates:
            return candidates[0]

        # Fallback to general
        return self._agents.get("general", SubAgent(name="general", description="Fallback"))

    def list_agents(self) -> List[SubAgent]:
        """Get all registered agents."""
        return list(self._agents.values())

    @property
    def agent_count(self) -> int:
        """Number of registered agents."""
        return len(self._agents)

    def agent_summary(self) -> str:
        """Get a summary of all agents and their capabilities."""
        lines = ["Sub-Agents:"]
        for agent in sorted(self._agents.values(), key=lambda a: -a.priority):
            caps = ", ".join(agent.capability_names) or "all"
            lines.append(f"  [{agent.name}] (priority:{agent.priority}) — {caps}")
        return "\n".join(lines)
