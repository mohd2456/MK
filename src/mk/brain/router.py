"""Brain Router — Uses the knowledge graph to handle requests locally.

This is MK's fast-path brain. Given user input, it checks the
knowledge graph for:
1. Direct commands (mapped to tools)
2. Known facts (answers without API)
3. Safety rules (dangerous actions)
4. Routing hints (local vs API)

If the graph can handle it → instant response, zero API cost.
If not → passes to the API layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mk.brain.graph import KnowledgeGraph


@dataclass
class BrainResponse:
    """Result from the brain router."""

    handled: bool = False          # Did the brain handle this locally?
    response: str = ""             # Text response (if handled)
    tool_call: Optional[Dict[str, Any]] = None  # Tool to execute (if applicable)
    needs_confirmation: bool = False  # Is this dangerous?
    risk_message: str = ""         # Why it's dangerous
    send_to_api: bool = False      # Should this go to an API?
    api_reason: str = ""           # Why it needs an API
    context: Dict[str, Any] = field(default_factory=dict)  # Extra context for API


class BrainRouter:
    """MK's local brain — routes requests using the knowledge graph.

    Checks patterns, keywords, and graph data to handle as much
    as possible without calling external APIs. Fast, free, offline.
    """

    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph
        self._command_patterns = self._build_command_patterns()
        self._danger_patterns = self._build_danger_patterns()

    def think(self, user_input: str) -> BrainResponse:
        """Process user input through the brain.

        This is the main entry point. Checks in order:
        1. Is it empty/greeting? → handle directly
        2. Is it a direct command? → route to tool
        3. Is it dangerous? → flag for confirmation
        4. Can the graph answer it? → answer from knowledge
        5. None of the above? → send to API

        Args:
            user_input: What the user said

        Returns:
            BrainResponse with the decision
        """
        text = user_input.strip().lower()

        if not text:
            return BrainResponse(handled=True, response="What's up?")

        # 1. Greetings / casual
        casual = self._check_casual(text)
        if casual:
            return casual

        # 2. Safety check FIRST (before commands, so dangerous stuff gets caught)
        danger = self._check_danger(text, user_input)
        if danger:
            return danger

        # 3. Direct commands (tool calls)
        command = self._check_commands(text)
        if command:
            return command

        # 4. Graph knowledge lookup
        knowledge = self._check_knowledge(text)
        if knowledge:
            return knowledge

        # 5. Can't handle locally → send to API
        return BrainResponse(
            handled=False,
            send_to_api=True,
            api_reason="Brain can't handle this locally — needs reasoning",
            context=self._build_api_context(text),
        )

    # ─── Casual / Greetings ───────────────────────────────

    def _check_casual(self, text: str) -> Optional[BrainResponse]:
        """Handle casual messages that don't need any processing."""
        greetings = {
            "hey": "What's good?",
            "hi": "Hey. What you need?",
            "yo": "Yo. What's up?",
            "sup": "Not much. What we doing?",
            "hello": "Hey. What can I do?",
            "good morning": "Morning. What's the plan?",
            "morning": "Morning. Systems are good. What you need?",
            "good night": "Night. I'll keep watch.",
            "gn": "Rest up. I got everything.",
            "thanks": "Bet.",
            "thank you": "Got you.",
            "ty": "Np.",
            "ok": "Need anything else?",
            "cool": "What's next?",
            "nvm": "Aight.",
            "nevermind": "Cancelled.",
            "you up": "Always. What you need?",
            "you there": "I'm here. What's up?",
        }

        for trigger, response in greetings.items():
            if text == trigger or text.rstrip("?!.") == trigger:
                return BrainResponse(handled=True, response=response)

        return None

    # ─── Command Matching ─────────────────────────────────

    def _build_command_patterns(self) -> List[Dict[str, Any]]:
        """Build regex patterns for direct command recognition."""
        return [
            # Docker restart
            {
                "pattern": r"(?:restart|reboot|bounce)\s+(\w+)",
                "tool": "docker",
                "action": "restart",
                "extract": "container",
            },
            # Docker stop (but NOT "shutdown the server" — that's dangerous)
            {
                "pattern": r"(?:stop|kill|turn\s*off)\s+(\w+)",
                "tool": "docker",
                "action": "stop",
                "extract": "container",
            },
            # Docker start
            {
                "pattern": r"(?:start|turn\s*on|spin\s*up|bring\s*up)\s+(\w+)",
                "tool": "docker",
                "action": "start",
                "extract": "container",
            },
            # Docker logs
            {
                "pattern": r"(?:logs?|show\s*logs?)\s+(?:for\s+)?(\w+)",
                "tool": "docker",
                "action": "logs",
                "extract": "container",
            },
            {
                "pattern": r"(\w+)\s+logs?",
                "tool": "docker",
                "action": "logs",
                "extract": "container",
            },
            # Status checks
            {
                "pattern": r"(?:status|check|how'?s?)\s+(?:the\s+)?(?:server|everything|all)",
                "tool": "system_monitor",
                "action": "all",
                "extract": None,
            },
            # Disk space
            {
                "pattern": r"(?:disk|space|storage|how\s*(?:much|full))",
                "tool": "ssh",
                "action": "command",
                "command": "df -h",
                "extract": None,
            },
            # RAM/memory
            {
                "pattern": r"(?:ram|memory|mem)\s*(?:usage|check|used)?",
                "tool": "ssh",
                "action": "command",
                "command": "free -h",
                "extract": None,
            },
            # What's running
            {
                "pattern": r"(?:what'?s?\s+running|list\s+containers|containers|show\s+containers)",
                "tool": "docker",
                "action": "list",
                "extract": None,
            },
            # Is X running (must come AFTER "what's running")
            {
                "pattern": r"(?:is\s+)?(\w+)\s+(?:running|up|working|alive)",
                "tool": "docker",
                "action": "status",
                "extract": "container",
            },
            # Media - download/get movie
            {
                "pattern": r"(?:grab|get|download|find)\s+(?:me\s+)?(.+?)(?:\s+movie)?$",
                "tool": "media",
                "action": "request_movie",
                "extract": "title",
            },
        ]

    def _check_commands(self, text: str) -> Optional[BrainResponse]:
        """Check if the input matches a known command pattern."""
        # Skip if input is too long (likely a complex request, not a command)
        if len(text.split()) > 8:
            return None

        # Skip if it starts with question/help words
        help_starters = ("help", "how", "why", "what should", "can you explain", "write", "create")
        if any(text.startswith(s) for s in help_starters):
            return None

        # First check: is the target a known service/container?
        for pattern_info in self._command_patterns:
            match = re.search(pattern_info["pattern"], text)
            if match:
                tool = pattern_info["tool"]
                action = pattern_info["action"]
                extract_key = pattern_info.get("extract")

                params: Dict[str, Any] = {"action": action}

                if extract_key and match.groups():
                    value = match.group(1).strip()
                    params[extract_key] = value

                    # Validate against graph — is this a known thing?
                    if extract_key == "container":
                        node = self.graph.get_node(value)
                        if node and node.kind == "service":
                            # Get the machine it runs on
                            machines = self.graph.get_related(value, "runs_on")
                            if machines:
                                params["machine"] = machines[0]
                        elif not node:
                            # Unknown container — still try but note it
                            params["machine"] = self._default_machine()

                if "command" in pattern_info:
                    params["command"] = pattern_info["command"]
                    params["machine"] = self._default_machine()

                if tool == "system_monitor":
                    params["machine"] = self._default_machine()

                return BrainResponse(
                    handled=True,
                    tool_call={"tool": tool, "params": params},
                )

        return None

    # ─── Safety Check ─────────────────────────────────────

    def _build_danger_patterns(self) -> List[Dict[str, str]]:
        """Patterns that indicate dangerous operations."""
        return [
            {"pattern": r"(?:delete|remove|rm)\s+(?:all|everything|\*|-rf)", "risk": "Permanent data deletion"},
            {"pattern": r"(?:wipe|format|nuke)", "risk": "Permanent data destruction"},
            {"pattern": r"(?:shutdown|shut\s*down|power\s*off)\s+(?:the\s+)?server", "risk": "All services go offline"},
            {"pattern": r"drop\s+(?:the\s+)?(?:database|db|table)", "risk": "Database destruction"},
            {"pattern": r"chmod\s+777", "risk": "Security vulnerability — world-writable files"},
            {"pattern": r"(?:disable|turn\s*off)\s+(?:the\s+)?firewall", "risk": "Server exposed to attacks"},
            {"pattern": r"(?:expose|open)\s+.*(?:internet|public|0\.0\.0\.0)", "risk": "Service exposed to internet"},
            {"pattern": r"reset\s+.*(?:to\s+default|factory)", "risk": "All configuration lost"},
            {"pattern": r"rm\s+-rf", "risk": "Recursive forced deletion"},
            {"pattern": r"mkfs", "risk": "Drive format — all data lost"},
            {"pattern": r"dd\s+if=", "risk": "Raw disk write — data destruction"},
        ]

    def _check_danger(self, text: str, original: str) -> Optional[BrainResponse]:
        """Check if the request is dangerous and needs confirmation."""
        for danger in self._danger_patterns:
            if re.search(danger["pattern"], text):
                return BrainResponse(
                    handled=True,
                    needs_confirmation=True,
                    risk_message=danger["risk"],
                    response=f"Hold up. That's dangerous: {danger['risk']}. You sure?",
                )
        return None

    # ─── Knowledge Lookup ─────────────────────────────────

    def _check_knowledge(self, text: str) -> Optional[BrainResponse]:
        """Check if the graph can directly answer the question."""
        # "What is X" / "What's X" / "Tell me about X"
        about_match = re.search(
            r"(?:what(?:'s|\s+is)\s+|tell\s+me\s+about\s+|info\s+(?:on|about)\s+)(\w+)",
            text,
        )
        if about_match:
            topic = about_match.group(1)
            node = self.graph.get_node(topic)
            if node:
                return self._describe_node(node)

        # "Where is X" / "What machine is X on"
        where_match = re.search(r"where(?:'s|\s+is)\s+(\w+)", text)
        if where_match:
            thing = where_match.group(1)
            machines = self.graph.get_related(thing, "runs_on")
            if machines:
                machine_node = self.graph.get_node(machines[0])
                host = machine_node.data.get("host", machines[0]) if machine_node else machines[0]
                return BrainResponse(
                    handled=True,
                    response=f"{thing} runs on {machines[0]} ({host}).",
                )

        # Direct node lookup by keyword
        nodes = self.graph.find_nodes(text)
        if len(nodes) == 1:
            return self._describe_node(nodes[0])

        return None

    def _describe_node(self, node) -> BrainResponse:
        """Build a description of a node from its data and connections."""
        parts = [f"{node.id} ({node.kind})"]

        if node.data:
            for k, v in node.data.items():
                if k not in ("created_at",):
                    parts.append(f"  {k}: {v}")

        # Get connections
        edges = self.graph.get_edges_from(node.id)
        for e in edges:
            parts.append(f"  → {e.relation} → {e.target}")

        edges_in = self.graph.get_edges_to(node.id)
        for e in edges_in:
            parts.append(f"  ← {e.relation} ← {e.source}")

        return BrainResponse(handled=True, response="\n".join(parts))

    # ─── API Context ──────────────────────────────────────

    def _build_api_context(self, text: str) -> Dict[str, Any]:
        """Build helpful context to send along with the API request.

        Pulls relevant info from the graph so the API has
        knowledge about the user's setup.
        """
        context: Dict[str, Any] = {}

        # Find any mentioned nodes
        mentioned_nodes = self.graph.find_nodes(text)
        if mentioned_nodes:
            context["relevant_entities"] = [
                {"id": n.id, "kind": n.kind, "data": n.data}
                for n in mentioned_nodes[:5]
            ]

        # Always include machine list
        machines = self.graph.get_nodes_by_kind("machine")
        if machines:
            context["machines"] = [
                {"id": m.id, "host": m.data.get("host", ""), "role": m.data.get("role", "")}
                for m in machines
            ]

        return context

    # ─── Helpers ──────────────────────────────────────────

    def _default_machine(self) -> str:
        """Get the default machine to run commands on."""
        machines = self.graph.get_nodes_by_kind("machine")
        # Prefer media-server if it exists
        for m in machines:
            if "media" in m.id.lower() or m.data.get("role") == "media":
                return m.id
        return machines[0].id if machines else "localhost"
