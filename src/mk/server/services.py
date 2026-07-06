"""Service Manager - Systemd service control, health monitoring, auto-restart.

The AI-managed service layer. Replaces Webmin/Cockpit service management:
- Full systemd service lifecycle (start, stop, restart, enable, disable)
- Service status and journal log access
- Health check integration with auto-restart policies
- Service creation (writing unit files)
- Timer management (cron replacement)
- Boot target management

MK monitors service health and takes action when things fail.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from .models import RestartPolicy, ServiceInfo, ServiceState

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages systemd services, timers, and system targets.

    Controls the entire service lifecycle through systemd.
    MK can start/stop services, read logs, create new service
    units, and set up health monitoring with auto-restart.
    """

    def __init__(self, sudo: bool = True) -> None:
        """Initialize the Service Manager.

        Args:
            sudo: Whether to prefix systemctl commands with sudo.
        """
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously.

        Args:
            cmd: Command to execute.
            check: Log errors on non-zero exit.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Service exec: {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        out = stdout.decode().strip()
        err = stderr.decode().strip()

        if rc != 0 and check:
            logger.error(f"Command failed ({rc}): {full_cmd}\n{err}")

        return rc, out, err

    # ─── Service Lifecycle ────────────────────────────────────────────────

    async def list_services(self, state_filter: Optional[str] = None) -> ToolResult:
        """List systemd services.

        Args:
            state_filter: Filter by state (running, failed, inactive).

        Returns:
            ToolResult with service listing.
        """
        state_arg = f"--state={state_filter}" if state_filter else ""
        rc, out, err = await self._run(
            f"systemctl list-units --type=service {state_arg} --no-pager --plain"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list services: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"filter": state_filter},
        )

    async def service_status(self, name: str) -> ToolResult:
        """Get detailed status of a service.

        Args:
            name: Service name (with or without .service suffix).

        Returns:
            ToolResult with service status.
        """
        if not name.endswith(".service"):
            name = f"{name}.service"

        rc, out, err = await self._run(f"systemctl status {name} --no-pager", check=False)

        # systemctl status returns non-zero for inactive/failed services
        # but still provides useful output
        if not out and rc != 0:
            return ToolResult(success=False, error=f"Service '{name}' not found: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"service": name},
        )

    async def start_service(self, name: str) -> ToolResult:
        """Start a service.

        Args:
            name: Service name.

        Returns:
            ToolResult with start status.
        """
        rc, out, err = await self._run(f"systemctl start {name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' started",
            side_effects=[f"Service '{name}' is now running"],
            metadata={"service": name, "action": "start"},
        )

    async def stop_service(self, name: str) -> ToolResult:
        """Stop a service.

        Args:
            name: Service name.

        Returns:
            ToolResult with stop status.
        """
        rc, out, err = await self._run(f"systemctl stop {name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to stop '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' stopped",
            side_effects=[f"Service '{name}' stopped"],
            metadata={"service": name, "action": "stop"},
        )

    async def restart_service(self, name: str) -> ToolResult:
        """Restart a service.

        Args:
            name: Service name.

        Returns:
            ToolResult with restart status.
        """
        rc, out, err = await self._run(f"systemctl restart {name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to restart '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' restarted",
            side_effects=[f"Service '{name}' restarted"],
            metadata={"service": name, "action": "restart"},
        )

    async def reload_service(self, name: str) -> ToolResult:
        """Reload a service's configuration without full restart.

        Args:
            name: Service name.

        Returns:
            ToolResult with reload status.
        """
        rc, out, err = await self._run(f"systemctl reload {name}")
        if rc != 0:
            # Fall back to restart if reload not supported
            return await self.restart_service(name)

        return ToolResult(
            success=True,
            output=f"Service '{name}' reloaded",
            side_effects=[f"Service '{name}' configuration reloaded"],
            metadata={"service": name, "action": "reload"},
        )

    async def enable_service(self, name: str, now: bool = False) -> ToolResult:
        """Enable a service to start on boot.

        Args:
            name: Service name.
            now: Also start the service immediately.

        Returns:
            ToolResult with enable status.
        """
        now_flag = "--now " if now else ""
        rc, out, err = await self._run(f"systemctl enable {now_flag}{name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to enable '{name}': {err}")

        msg = f"Service '{name}' enabled for boot"
        if now:
            msg += " and started"

        return ToolResult(
            success=True,
            output=msg,
            side_effects=[f"Service '{name}' will start on boot"],
            metadata={"service": name, "action": "enable", "started": now},
        )

    async def disable_service(self, name: str, now: bool = False) -> ToolResult:
        """Disable a service from starting on boot.

        Args:
            name: Service name.
            now: Also stop the service immediately.

        Returns:
            ToolResult with disable status.
        """
        now_flag = "--now " if now else ""
        rc, out, err = await self._run(f"systemctl disable {now_flag}{name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to disable '{name}': {err}")

        msg = f"Service '{name}' disabled from boot"
        if now:
            msg += " and stopped"

        return ToolResult(
            success=True,
            output=msg,
            side_effects=[f"Service '{name}' will not start on boot"],
            metadata={"service": name, "action": "disable", "stopped": now},
        )

    # ─── Journal Logs ─────────────────────────────────────────────────────

    async def service_logs(
        self,
        name: str,
        lines: int = 100,
        since: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> ToolResult:
        """Get journal logs for a service.

        Args:
            name: Service name.
            lines: Number of recent lines.
            since: Time filter (e.g., "1h ago", "today", "2024-01-01").
            priority: Minimum priority (emerg, alert, crit, err, warning, notice, info, debug).

        Returns:
            ToolResult with log output.
        """
        cmd_parts = [f"journalctl -u {name} --no-pager -n {lines}"]
        if since:
            cmd_parts.append(f'--since="{since}"')
        if priority:
            cmd_parts.append(f"--priority={priority}")

        cmd = " ".join(cmd_parts)
        rc, out, err = await self._run(cmd, check=False)

        return ToolResult(
            success=True,
            output=out if out else "(no logs found)",
            metadata={"service": name, "lines": lines},
        )

    async def system_logs(
        self, lines: int = 50, since: Optional[str] = None, priority: str = "err"
    ) -> ToolResult:
        """Get system-wide journal logs filtered by priority.

        Args:
            lines: Number of recent lines.
            since: Time filter.
            priority: Minimum priority level.

        Returns:
            ToolResult with system logs.
        """
        cmd_parts = [f"journalctl --no-pager -n {lines} --priority={priority}"]
        if since:
            cmd_parts.append(f'--since="{since}"')

        cmd = " ".join(cmd_parts)
        rc, out, err = await self._run(cmd, check=False)

        return ToolResult(
            success=True,
            output=out if out else "(no logs found)",
            metadata={"scope": "system", "priority": priority},
        )

    # ─── Service Creation ─────────────────────────────────────────────────

    async def create_service(
        self,
        name: str,
        exec_start: str,
        description: str = "",
        working_directory: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None,
        restart: str = "on-failure",
        restart_sec: int = 5,
        environment: Optional[Dict[str, str]] = None,
        after: Optional[List[str]] = None,
        wants: Optional[List[str]] = None,
        enable: bool = True,
    ) -> ToolResult:
        """Create a new systemd service unit file.

        Args:
            name: Service name (without .service suffix).
            exec_start: Command to run.
            description: Service description.
            working_directory: Working directory for the process.
            user: Run as this user.
            group: Run as this group.
            restart: Restart policy (always, on-failure, no).
            restart_sec: Seconds to wait before restart.
            environment: Environment variables.
            after: Units to start after.
            wants: Units that are wanted (soft dependency).
            enable: Enable the service after creation.

        Returns:
            ToolResult with creation status.
        """
        # Build unit file
        unit_lines = ["[Unit]"]
        unit_lines.append(f"Description={description or name}")
        if after:
            unit_lines.append(f"After={' '.join(after)}")
        else:
            unit_lines.append("After=network.target")
        if wants:
            unit_lines.append(f"Wants={' '.join(wants)}")

        unit_lines.append("")
        unit_lines.append("[Service]")
        unit_lines.append("Type=simple")
        unit_lines.append(f"ExecStart={exec_start}")
        unit_lines.append(f"Restart={restart}")
        unit_lines.append(f"RestartSec={restart_sec}")

        if working_directory:
            unit_lines.append(f"WorkingDirectory={working_directory}")
        if user:
            unit_lines.append(f"User={user}")
        if group:
            unit_lines.append(f"Group={group}")
        if environment:
            for key, value in environment.items():
                unit_lines.append(f"Environment={key}={value}")

        unit_lines.append("")
        unit_lines.append("[Install]")
        unit_lines.append("WantedBy=multi-user.target")

        unit_content = "\n".join(unit_lines) + "\n"
        unit_path = f"/etc/systemd/system/{name}.service"

        # Write unit file
        rc, _, err = await self._run(
            f"bash -c 'cat > {unit_path} << MKEOF\n{unit_content}MKEOF'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write unit file: {err}")

        # Reload systemd
        await self._run("systemctl daemon-reload")

        # Enable if requested
        if enable:
            await self._run(f"systemctl enable {name}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' created at {unit_path}",
            side_effects=[
                f"Unit file written to {unit_path}",
                "systemd daemon reloaded",
                f"Service {'enabled' if enable else 'not enabled'}",
            ],
            metadata={"service": name, "path": unit_path, "enabled": enable},
        )

    async def delete_service(self, name: str) -> ToolResult:
        """Delete a systemd service unit.

        Args:
            name: Service name.

        Returns:
            ToolResult with deletion status.
        """
        # Stop and disable first
        await self._run(f"systemctl stop {name}", check=False)
        await self._run(f"systemctl disable {name}", check=False)

        # Remove unit file
        unit_path = f"/etc/systemd/system/{name}.service"
        rc, _, err = await self._run(f"rm -f {unit_path}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to delete unit file: {err}")

        # Reload
        await self._run("systemctl daemon-reload")

        return ToolResult(
            success=True,
            output=f"Service '{name}' deleted",
            side_effects=[f"Unit file {unit_path} removed", "Service stopped and disabled"],
            metadata={"service": name, "action": "delete"},
        )

    # ─── Timer Management (cron replacement) ──────────────────────────────

    async def list_timers(self) -> ToolResult:
        """List all systemd timers.

        Returns:
            ToolResult with timer listing.
        """
        rc, out, err = await self._run(
            "systemctl list-timers --all --no-pager"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list timers: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"format": "systemd_timers"},
        )

    async def create_timer(
        self,
        name: str,
        on_calendar: str,
        service_name: Optional[str] = None,
        description: str = "",
        persistent: bool = True,
    ) -> ToolResult:
        """Create a systemd timer (cron replacement).

        Args:
            name: Timer name (without .timer suffix).
            on_calendar: Calendar expression (e.g., "daily", "*-*-* 02:00:00", "hourly").
            service_name: Service to trigger (defaults to name.service).
            description: Timer description.
            persistent: Run immediately if missed while system was off.

        Returns:
            ToolResult with timer creation status.
        """
        target_service = service_name or name

        timer_content = f"""[Unit]
Description={description or f'Timer for {target_service}'}

[Timer]
OnCalendar={on_calendar}
Persistent={'true' if persistent else 'false'}
Unit={target_service}.service

[Install]
WantedBy=timers.target
"""

        timer_path = f"/etc/systemd/system/{name}.timer"
        rc, _, err = await self._run(
            f"bash -c 'cat > {timer_path} << MKEOF\n{timer_content}MKEOF'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write timer: {err}")

        await self._run("systemctl daemon-reload")
        await self._run(f"systemctl enable --now {name}.timer")

        return ToolResult(
            success=True,
            output=f"Timer '{name}' created (schedule: {on_calendar})",
            side_effects=[
                f"Timer file written to {timer_path}",
                f"Timer enabled and active, triggers {target_service}.service",
            ],
            metadata={"timer": name, "schedule": on_calendar, "service": target_service},
        )

    # ─── System State ─────────────────────────────────────────────────────

    async def failed_services(self) -> ToolResult:
        """List all failed services for quick triage.

        Returns:
            ToolResult with failed service listing.
        """
        rc, out, err = await self._run(
            "systemctl list-units --state=failed --no-pager --plain"
        )

        return ToolResult(
            success=True,
            output=out if out else "No failed services",
            metadata={"scope": "failed"},
        )

    async def system_boot_time(self) -> ToolResult:
        """Get system boot analysis.

        Returns:
            ToolResult with boot timing info.
        """
        rc, out, err = await self._run("systemd-analyze", check=False)
        rc2, blame, _ = await self._run("systemd-analyze blame --no-pager | head -20", check=False)

        result = out or ""
        if blame:
            result += f"\n\nSlowest services:\n{blame}"

        return ToolResult(
            success=True,
            output=result if result else "Boot analysis unavailable",
            metadata={"format": "boot_analysis"},
        )

    async def reload_daemon(self) -> ToolResult:
        """Reload systemd manager configuration (daemon-reload).

        Returns:
            ToolResult with reload status.
        """
        rc, out, err = await self._run("systemctl daemon-reload")
        if rc != 0:
            return ToolResult(success=False, error=f"Daemon reload failed: {err}")

        return ToolResult(
            success=True,
            output="Systemd daemon reloaded",
            side_effects=["systemd configuration reloaded"],
            metadata={"action": "daemon-reload"},
        )
