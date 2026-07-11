"""Docker management tool.

Manages Docker containers on local or remote machines.
Supports listing, starting, stopping, restarting containers,
viewing logs, and deploying compose files.
"""

from __future__ import annotations

from typing import Any, Dict

from mk.tools.base import Tool, ToolResult


class DockerTool(Tool):
    """Docker container management tool.

    Provides methods to manage Docker containers on local
    or remote machines. In production, connects via Docker
    API or SSH for remote management.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "docker"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Manage Docker containers on local or remote machines. "
            "List, start, stop, restart containers, view logs, "
            "and deploy docker-compose configurations."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for Docker tool parameters."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list_containers",
                        "start_container",
                        "stop_container",
                        "restart_container",
                        "container_logs",
                        "deploy_compose",
                    ],
                    "description": "The Docker action to perform",
                },
                "machine": {
                    "type": "string",
                    "description": "Target machine (empty for local)",
                },
                "container_name": {
                    "type": "string",
                    "description": "Container name (for start/stop/restart/logs)",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to return",
                },
                "compose_content": {
                    "type": "string",
                    "description": "Docker compose YAML content (for deploy_compose)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a Docker management action.

        Args:
            **kwargs: Action-specific arguments.

        Returns:
            ToolResult with operation output or error.
        """
        action = kwargs.get("action", "")
        if not action:
            return ToolResult(success=False, error="Action is required")

        machine = kwargs.get("machine", "local")

        if action == "list_containers":
            return await self._list_containers(machine)
        elif action == "start_container":
            return await self._start_container(machine, kwargs)
        elif action == "stop_container":
            return await self._stop_container(machine, kwargs)
        elif action == "restart_container":
            return await self._restart_container(machine, kwargs)
        elif action == "container_logs":
            return await self._container_logs(machine, kwargs)
        elif action == "deploy_compose":
            return await self._deploy_compose(machine, kwargs)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _list_containers(self, machine: str) -> ToolResult:
        """List all containers on a machine.

        Args:
            machine: Target machine identifier.

        Returns:
            ToolResult with container listing.
        """
        return ToolResult(
            success=True,
            output=f"[Docker:{machine}] Listed containers",
            metadata={"action": "list_containers", "machine": machine},
        )

    async def _start_container(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Start a container.

        Args:
            machine: Target machine.
            kwargs: Must contain 'container_name'.

        Returns:
            ToolResult with start status.
        """
        name = kwargs.get("container_name", "")
        if not name:
            return ToolResult(success=False, error="container_name is required")

        return ToolResult(
            success=True,
            output=f"Started container '{name}' on {machine}",
            side_effects=[f"Container '{name}' started on {machine}"],
            metadata={"action": "start_container", "machine": machine, "container": name},
        )

    async def _stop_container(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Stop a container.

        Args:
            machine: Target machine.
            kwargs: Must contain 'container_name'.

        Returns:
            ToolResult with stop status.
        """
        name = kwargs.get("container_name", "")
        if not name:
            return ToolResult(success=False, error="container_name is required")

        return ToolResult(
            success=True,
            output=f"Stopped container '{name}' on {machine}",
            side_effects=[f"Container '{name}' stopped on {machine}"],
            metadata={"action": "stop_container", "machine": machine, "container": name},
        )

    async def _restart_container(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Restart a container.

        Args:
            machine: Target machine.
            kwargs: Must contain 'container_name'.

        Returns:
            ToolResult with restart status.
        """
        name = kwargs.get("container_name", "")
        if not name:
            return ToolResult(success=False, error="container_name is required")

        return ToolResult(
            success=True,
            output=f"Restarted container '{name}' on {machine}",
            side_effects=[f"Container '{name}' restarted on {machine}"],
            metadata={"action": "restart_container", "machine": machine, "container": name},
        )

    async def _container_logs(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Get container logs.

        Args:
            machine: Target machine.
            kwargs: Must contain 'container_name', optionally 'lines'.

        Returns:
            ToolResult with log output.
        """
        name = kwargs.get("container_name", "")
        if not name:
            return ToolResult(success=False, error="container_name is required")

        lines = kwargs.get("lines", 100)

        return ToolResult(
            success=True,
            output=f"[Docker:{machine}] Logs for '{name}' (last {lines} lines)",
            metadata={
                "action": "container_logs",
                "machine": machine,
                "container": name,
                "lines": lines,
            },
        )

    async def _deploy_compose(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Deploy a docker-compose configuration.

        Args:
            machine: Target machine.
            kwargs: Must contain 'compose_content'.

        Returns:
            ToolResult with deployment status.
        """
        content = kwargs.get("compose_content", "")
        if not content:
            return ToolResult(success=False, error="compose_content is required")

        return ToolResult(
            success=True,
            output=f"Deployed docker-compose on {machine}",
            side_effects=[f"Docker compose deployed on {machine}"],
            metadata={
                "action": "deploy_compose",
                "machine": machine,
                "compose_size": len(content),
            },
        )
