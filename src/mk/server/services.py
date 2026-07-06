"""Service Manager - Systemd service control, health monitoring, auto-restart."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from ._shell import safe_quote, validate_name
from .models import RestartPolicy, ServiceInfo, ServiceState

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages systemd services, timers, and system targets."""

    def __init__(self, sudo: bool = True) -> None:
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
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

    async def _run_with_stdin(self, cmd: str, input_data: str) -> Tuple[int, str, str]:
        """Execute a shell command with data passed via stdin."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Service exec (stdin): {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=input_data.encode())
        rc = proc.returncode or 0
        return rc, stdout.decode().strip(), stderr.decode().strip()

    # Service Lifecycle

    async def list_services(self, state_filter: Optional[str] = None) -> ToolResult:
        """List systemd services."""
        state_arg = f"--state={safe_quote(state_filter)}" if state_filter else ""
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
        """Get detailed status of a service."""
        validate_name(name, "service name")
        if not name.endswith(".service"):
            name = f"{name}.service"

        rc, out, err = await self._run(f"systemctl status {safe_quote(name)} --no-pager", check=False)

        if not out and rc != 0:
            return ToolResult(success=False, error=f"Service '{name}' not found: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"service": name},
        )

    async def start_service(self, name: str) -> ToolResult:
        """Start a service."""
        validate_name(name, "service name")
        rc, out, err = await self._run(f"systemctl start {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' started",
            side_effects=[f"Service '{name}' is now running"],
            metadata={"service": name, "action": "start"},
        )

    async def stop_service(self, name: str) -> ToolResult:
        """Stop a service."""
        validate_name(name, "service name")
        rc, out, err = await self._run(f"systemctl stop {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to stop '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' stopped",
            side_effects=[f"Service '{name}' stopped"],
            metadata={"service": name, "action": "stop"},
        )

    async def restart_service(self, name: str) -> ToolResult:
        """Restart a service."""
        validate_name(name, "service name")
        rc, out, err = await self._run(f"systemctl restart {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to restart '{name}': {err}")

        return ToolResult(
            success=True,
            output=f"Service '{name}' restarted",
            side_effects=[f"Service '{name}' restarted"],
            metadata={"service": name, "action": "restart"},
        )

    async def reload_service(self, name: str) -> ToolResult:
        """Reload a service's configuration without full restart."""
        validate_name(name, "service name")
        rc, out, err = await self._run(f"systemctl reload {safe_quote(name)}")
        if rc != 0:
            return await self.restart_service(name)

        return ToolResult(
            success=True,
            output=f"Service '{name}' reloaded",
            side_effects=[f"Service '{name}' configuration reloaded"],
            metadata={"service": name, "action": "reload"},
        )

    async def enable_service(self, name: str, now: bool = False) -> ToolResult:
        """Enable a service to start on boot."""
        validate_name(name, "service name")
        now_flag = "--now " if now else ""
        rc, out, err = await self._run(f"systemctl enable {now_flag}{safe_quote(name)}")
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
        """Disable a service from starting on boot."""
        validate_name(name, "service name")
        now_flag = "--now " if now else ""
        rc, out, err = await self._run(f"systemctl disable {now_flag}{safe_quote(name)}")
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

    # Journal Logs

    async def service_logs(
        self,
        name: str,
        lines: int = 100,
        since: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> ToolResult:
        """Get journal logs for a service."""
        validate_name(name, "service name")
        cmd_parts = [f"journalctl -u {safe_quote(name)} --no-pager -n {int(lines)}"]
        if since:
            cmd_parts.append(f"--since={safe_quote(since)}")
        if priority:
            cmd_parts.append(f"--priority={safe_quote(priority)}")

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
        """Get system-wide journal logs filtered by priority."""
        cmd_parts = [f"journalctl --no-pager -n {int(lines)} --priority={safe_quote(priority)}"]
        if since:
            cmd_parts.append(f"--since={safe_quote(since)}")

        cmd = " ".join(cmd_parts)
        rc, out, err = await self._run(cmd, check=False)

        return ToolResult(
            success=True,
            output=out if out else "(no logs found)",
            metadata={"scope": "system", "priority": priority},
        )

    # Service Creation

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
        """Create a new systemd service unit file."""
        validate_name(name, "service name")

        # Build unit file content
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
            validate_name(user, "user")
            unit_lines.append(f"User={user}")
        if group:
            validate_name(group, "group")
            unit_lines.append(f"Group={group}")
        if environment:
            for key, value in environment.items():
                # Quote the value in the unit file to handle special chars
                unit_lines.append(f'Environment="{key}={value}"')

        unit_lines.append("")
        unit_lines.append("[Install]")
        unit_lines.append("WantedBy=multi-user.target")

        unit_content = "\n".join(unit_lines) + "\n"
        unit_path = f"/etc/systemd/system/{name}.service"

        # Write unit file via stdin to avoid shell interpolation
        rc, _, err = await self._run_with_stdin(
            f"tee {safe_quote(unit_path)} > /dev/null", unit_content
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write unit file: {err}")

        await self._run("systemctl daemon-reload")

        if enable:
            await self._run(f"systemctl enable {safe_quote(name)}")

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
        """Delete a systemd service unit."""
        validate_name(name, "service name")
        await self._run(f"systemctl stop {safe_quote(name)}", check=False)
        await self._run(f"systemctl disable {safe_quote(name)}", check=False)

        unit_path = f"/etc/systemd/system/{name}.service"
        rc, _, err = await self._run(f"rm -f {safe_quote(unit_path)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to delete unit file: {err}")

        await self._run("systemctl daemon-reload")

        return ToolResult(
            success=True,
            output=f"Service '{name}' deleted",
            side_effects=[f"Unit file {unit_path} removed", "Service stopped and disabled"],
            metadata={"service": name, "action": "delete"},
        )

    # Timer Management

    async def list_timers(self) -> ToolResult:
        """List all systemd timers."""
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
        """Create a systemd timer (cron replacement)."""
        validate_name(name, "timer name")
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
        rc, _, err = await self._run_with_stdin(
            f"tee {safe_quote(timer_path)} > /dev/null", timer_content
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write timer: {err}")

        await self._run("systemctl daemon-reload")
        await self._run(f"systemctl enable --now {safe_quote(name)}.timer")

        return ToolResult(
            success=True,
            output=f"Timer '{name}' created (schedule: {on_calendar})",
            side_effects=[
                f"Timer file written to {timer_path}",
                f"Timer enabled and active, triggers {target_service}.service",
            ],
            metadata={"timer": name, "schedule": on_calendar, "service": target_service},
        )

    # System State

    async def failed_services(self) -> ToolResult:
        """List all failed services."""
        rc, out, err = await self._run(
            "systemctl list-units --state=failed --no-pager --plain"
        )

        return ToolResult(
            success=True,
            output=out if out else "No failed services",
            metadata={"scope": "failed"},
        )

    async def system_boot_time(self) -> ToolResult:
        """Get system boot analysis."""
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
        """Reload systemd manager configuration (daemon-reload)."""
        rc, out, err = await self._run("systemctl daemon-reload")
        if rc != 0:
            return ToolResult(success=False, error=f"Daemon reload failed: {err}")

        return ToolResult(
            success=True,
            output="Systemd daemon reloaded",
            side_effects=["systemd configuration reloaded"],
            metadata={"action": "daemon-reload"},
        )
