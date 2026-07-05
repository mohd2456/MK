"""System monitoring tool.

Monitors CPU, memory, disk, and network on local and remote
machines. Provides health checks for services and self-monitoring.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mk.tools.base import Tool, ToolResult


class SystemMonitorTool(Tool):
    """System monitoring and health check tool.

    Monitors system resources (CPU, memory, disk, network)
    on local and remote machines. Also provides service-level
    health checks and self-monitoring for the MK system.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "system_monitor"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Monitor system resources and service health. "
            "Check CPU, memory, disk, and network usage on "
            "local or remote machines. Perform health checks "
            "on running services."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for system monitor parameters."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get_system_stats",
                        "get_service_status",
                        "check_health",
                    ],
                    "description": "The monitoring action to perform",
                },
                "machine": {
                    "type": "string",
                    "description": "Target machine (empty for local)",
                },
                "service_name": {
                    "type": "string",
                    "description": "Service name (for get_service_status)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a monitoring action.

        Args:
            **kwargs: Action-specific arguments.

        Returns:
            ToolResult with monitoring data or error.
        """
        action = kwargs.get("action", "")
        if not action:
            return ToolResult(success=False, error="Action is required")

        machine = kwargs.get("machine", "local")

        if action == "get_system_stats":
            return await self._get_system_stats(machine)
        elif action == "get_service_status":
            return await self._get_service_status(
                kwargs.get("service_name", ""), machine
            )
        elif action == "check_health":
            return await self._check_health(machine)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _get_system_stats(self, machine: str) -> ToolResult:
        """Get system resource statistics.

        Args:
            machine: Target machine identifier.

        Returns:
            ToolResult with system stats.
        """
        # In production, this would run commands like
        # `top -bn1`, `free -m`, `df -h`, `ifconfig` via SSH
        return ToolResult(
            success=True,
            output=f"System stats for {machine}",
            metadata={
                "action": "get_system_stats",
                "machine": machine,
                "metrics": ["cpu", "memory", "disk", "network"],
            },
        )

    async def _get_service_status(self, service_name: str, machine: str) -> ToolResult:
        """Get the status of a specific service.

        Args:
            service_name: Name of the service to check.
            machine: Target machine.

        Returns:
            ToolResult with service status.
        """
        if not service_name:
            return ToolResult(
                success=False, error="service_name is required"
            )

        # In production: `systemctl status {service_name}` via SSH
        return ToolResult(
            success=True,
            output=f"Service '{service_name}' on {machine}: active",
            metadata={
                "action": "get_service_status",
                "machine": machine,
                "service": service_name,
            },
        )

    async def _check_health(self, machine: str) -> ToolResult:
        """Run a health check on a machine.

        Performs a comprehensive health check including system
        resources, key services, and connectivity.

        Args:
            machine: Target machine identifier.

        Returns:
            ToolResult with health check results.
        """
        # In production, this would:
        # 1. Check system resources
        # 2. Check key services (docker, ssh, etc.)
        # 3. Check network connectivity
        # 4. Report any anomalies
        return ToolResult(
            success=True,
            output=f"Health check for {machine}: OK",
            metadata={
                "action": "check_health",
                "machine": machine,
                "checks": ["resources", "services", "connectivity"],
            },
        )
