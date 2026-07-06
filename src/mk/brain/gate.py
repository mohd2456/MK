"""API Gate — Decides when the brain needs external help.

The gate sits between the brain and the API layer.
If the brain handled the request → done, no API call.
If the brain says "send to API" → the gate adds context
from the graph and forwards to the cheapest/best provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from mk.brain.graph import KnowledgeGraph
from mk.brain.router import BrainResponse, BrainRouter


@dataclass
class GateResult:
    """Final result after the brain + gate process."""

    source: str              # "brain" or "api"
    response: str = ""       # Final text response
    tool_call: Optional[Dict[str, Any]] = None  # Tool to execute
    needs_confirmation: bool = False
    risk_message: str = ""
    api_request: Optional[Dict[str, Any]] = None  # Prepared API request (if needed)


class APIGate:
    """The gate between MK's local brain and external APIs.

    Flow:
    1. User input → BrainRouter.think()
    2. If handled → return result (no API)
    3. If not handled → prepare API request with graph context
    4. Return prepared request for the API layer to execute

    The gate doesn't call APIs itself — it just decides and prepares.
    The actual API call happens in the engine layer.
    """

    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph
        self.brain = BrainRouter(graph)

    def process(self, user_input: str) -> GateResult:
        """Process user input through brain, decide if API is needed.

        Args:
            user_input: What the user said

        Returns:
            GateResult with either a local answer or a prepared API request
        """
        # Let the brain try first
        brain_result = self.brain.think(user_input)

        # Brain handled it locally
        if brain_result.handled and not brain_result.send_to_api:
            return GateResult(
                source="brain",
                response=brain_result.response,
                tool_call=brain_result.tool_call,
                needs_confirmation=brain_result.needs_confirmation,
                risk_message=brain_result.risk_message,
            )

        # Brain says send to API — prepare the request
        api_request = self._prepare_api_request(user_input, brain_result)

        return GateResult(
            source="api",
            api_request=api_request,
        )

    def _prepare_api_request(
        self, user_input: str, brain_result: BrainResponse
    ) -> Dict[str, Any]:
        """Prepare an efficient API request with graph context.

        Keeps tokens LOW by only including relevant context.

        Args:
            user_input: Original user input
            brain_result: What the brain figured out

        Returns:
            Dict ready to be sent to the API layer
        """
        # Build system context from graph (short, token-efficient)
        system_parts = ["You are MK, a personal AI operating system."]
        system_parts.append("Keep responses short and actionable.")

        # Add machine context
        machines = self.graph.get_nodes_by_kind("machine")
        if machines:
            machine_list = ", ".join(
                f"{m.id}({m.data.get('host', '?')})" for m in machines
            )
            system_parts.append(f"Homelab machines: {machine_list}")

        # Add relevant entities from brain context
        if brain_result.context.get("relevant_entities"):
            entities = brain_result.context["relevant_entities"]
            entity_str = ", ".join(
                f"{e['id']}({e['kind']})" for e in entities
            )
            system_parts.append(f"Relevant: {entity_str}")

        # Add tool list (short form)
        tools = self.graph.get_nodes_by_kind("tool")
        if tools:
            tool_names = ", ".join(t.id for t in tools)
            system_parts.append(f"Available tools: {tool_names}")

        # Add user preferences if any
        prefs = self.graph.get_nodes_by_kind("preference")
        if prefs:
            pref_str = "; ".join(
                f"{p.id}={p.data.get('value', '')}" for p in prefs[:5]
            )
            system_parts.append(f"User prefs: {pref_str}")

        system_prompt = " ".join(system_parts)

        return {
            "system_prompt": system_prompt,
            "user_message": user_input,
            "context": brain_result.context,
            "reason": brain_result.api_reason,
        }

    def teach(self, key: str, value: str, kind: str = "fact", **data) -> None:
        """Teach MK something new (add to graph).

        Args:
            key: Node ID / fact name
            value: The information
            kind: Node type (fact, preference, machine, service)
            **data: Extra data
        """
        self.graph.add_node(key, kind=kind, value=value, **data)
        self.graph.save()

    def forget(self, key: str) -> bool:
        """Remove something from MK's knowledge.

        Args:
            key: Node ID to remove

        Returns:
            True if removed
        """
        result = self.graph.remove_node(key)
        if result:
            self.graph.save()
        return result

    def setup_homelab(self, machines: Dict[str, Dict[str, str]]) -> None:
        """Quick setup — add machines and services to the graph.

        Args:
            machines: Dict of machine_id → {host, role, services: [list]}

        Example:
            gate.setup_homelab({
                "media-server": {
                    "host": "192.168.1.50",
                    "role": "media",
                    "services": ["plex", "sonarr", "radarr"]
                },
                "mk-brain": {
                    "host": "192.168.1.10",
                    "role": "orchestrator",
                    "services": []
                }
            })
        """
        for machine_id, info in machines.items():
            self.graph.add_node(
                machine_id,
                kind="machine",
                host=info.get("host", ""),
                role=info.get("role", ""),
            )

            for service in info.get("services", []):
                self.graph.add_node(service, kind="service")
                self.graph.add_edge(service, machine_id, "runs_on")

        # Add default tools
        for tool in ["ssh", "docker", "media", "files", "system_monitor"]:
            self.graph.add_node(tool, kind="tool")

        self.graph.save()
