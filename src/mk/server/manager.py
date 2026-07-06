"""ServerManager - The top-level orchestrator for MK OS server management.

This is the single entry point that ties all sub-managers together.
MK's brain routes server-related requests here, and the ServerManager
delegates to the appropriate sub-system (storage, containers, network,
services, backups, users).

Also provides cross-cutting concerns:
- Full system overview / dashboard
- Health aggregation across all subsystems
- Power management (reboot, shutdown)
- System info and hardware inventory
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

from mk.tools.base import ToolResult

from .backups import BackupManager
from .containers import ContainerManager
from .network import NetworkManager
from .services import ServiceManager
from .storage import StorageManager
from .users import UserManager

logger = logging.getLogger(__name__)


class ServerManager:
    """Top-level orchestrator for all MK OS server management.

    Initializes and holds references to all sub-managers.
    Provides system-wide operations and a unified health view.

    This is what MK's brain talks to — one object that manages
    the entire server.
    """

    def __init__(
        self,
        sudo: bool = True,
        compose_dir: str = "/opt/mk/stacks",
        backup_config_dir: str = "/etc/mk/backups",
        backup_state_dir: str = "/var/lib/mk/backups",
    ) -> None:
        """Initialize the ServerManager and all sub-managers.

        Args:
            sudo: Whether sub-managers should use sudo.
            compose_dir: Base directory for Docker Compose stacks.
            backup_config_dir: Directory for backup job configs.
            backup_state_dir: Directory for backup state data.
        """
        self.storage = StorageManager(sudo=sudo)
        self.containers = ContainerManager(sudo=False, compose_dir=compose_dir)
        self.network = NetworkManager(sudo=sudo)
        self.services = ServiceManager(sudo=sudo)
        self.backups = BackupManager(
            sudo=sudo,
            config_dir=backup_config_dir,
            state_dir=backup_state_dir,
        )
        self.users = UserManager(sudo=sudo)

        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Server exec: {full_cmd}")

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


    # ─── System Overview ──────────────────────────────────────────────────

    async def system_overview(self) -> ToolResult:
        """Get a complete system overview — the AI dashboard.

        Aggregates key info from all subsystems into one view:
        hostname, uptime, CPU/RAM/disk, containers, services, network.

        Returns:
            ToolResult with full system overview.
        """
        overview: Dict[str, Any] = {}

        # Hostname and OS
        rc, hostname, _ = await self._run("hostname", check=False)
        overview["hostname"] = hostname or "unknown"

        rc, os_info, _ = await self._run(
            "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
            check=False,
        )
        overview["os"] = os_info or "unknown"

        # Kernel
        rc, kernel, _ = await self._run("uname -r", check=False)
        overview["kernel"] = kernel or "unknown"

        # Uptime
        rc, uptime, _ = await self._run("uptime -p", check=False)
        overview["uptime"] = uptime or "unknown"

        # CPU info
        rc, cpu_info, _ = await self._run(
            "lscpu | grep 'Model name' | cut -d: -f2 | xargs",
            check=False,
        )
        rc2, cpu_cores, _ = await self._run("nproc", check=False)
        overview["cpu"] = {
            "model": cpu_info or "unknown",
            "cores": int(cpu_cores) if cpu_cores else 0,
        }

        # Load average
        rc, load, _ = await self._run("cat /proc/loadavg", check=False)
        if load:
            parts = load.split()
            overview["load_average"] = {
                "1min": float(parts[0]),
                "5min": float(parts[1]),
                "15min": float(parts[2]),
            }

        # Memory
        rc, mem, _ = await self._run(
            "free -b | awk '/Mem:/{print $2,$3,$7}'",
            check=False,
        )
        if mem:
            parts = mem.split()
            total = int(parts[0])
            used = int(parts[1])
            available = int(parts[2]) if len(parts) > 2 else total - used
            overview["memory"] = {
                "total_gb": round(total / (1024**3), 1),
                "used_gb": round(used / (1024**3), 1),
                "available_gb": round(available / (1024**3), 1),
                "percent_used": round(used / total * 100, 1) if total > 0 else 0,
            }

        # Disk (root filesystem)
        rc, disk, _ = await self._run(
            "df -B1 / | awk 'NR==2{print $2,$3,$4,$5}'",
            check=False,
        )
        if disk:
            parts = disk.split()
            overview["disk_root"] = {
                "total_gb": round(int(parts[0]) / (1024**3), 1),
                "used_gb": round(int(parts[1]) / (1024**3), 1),
                "free_gb": round(int(parts[2]) / (1024**3), 1),
                "percent_used": parts[3] if len(parts) > 3 else "0%",
            }

        # Docker container summary
        rc, containers, _ = await self._run(
            "docker ps --format '{{.State}}' 2>/dev/null | sort | uniq -c",
            check=False,
        )
        if rc == 0 and containers:
            overview["containers"] = containers
        else:
            overview["containers"] = "Docker not available"

        # Failed services
        rc, failed, _ = await self._run(
            "systemctl list-units --state=failed --no-pager --plain --no-legend 2>/dev/null | wc -l",
            check=False,
        )
        overview["failed_services"] = int(failed) if failed and failed.isdigit() else 0

        # Network interfaces with IPs
        rc, ips, _ = await self._run(
            "ip -4 addr show | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}/\\d+' | head -5",
            check=False,
        )
        overview["ipv4_addresses"] = ips.splitlines() if ips else []

        return ToolResult(
            success=True,
            output=json.dumps(overview, indent=2),
            metadata={"type": "system_overview", "overview": overview},
        )


    async def health_report(self) -> ToolResult:
        """Aggregated health report across all subsystems.

        Checks:
        - Storage pool health
        - Container health
        - Failed services
        - Backup job health
        - Network connectivity
        - Disk space warnings

        Returns:
            ToolResult with health summary and issues.
        """
        issues: list = []
        checks_passed = 0
        total_checks = 0

        # 1. Storage health
        total_checks += 1
        storage_result = await self.storage.list_pools()
        if storage_result.success:
            pools = storage_result.metadata.get("pools", [])
            for pool in pools:
                status = pool.get("status", "unknown")
                if status != "online":
                    issues.append(f"STORAGE: Pool '{pool['name']}' is {status}")
            if not any(p.get("status") != "online" for p in pools):
                checks_passed += 1
        else:
            # No ZFS — not necessarily an issue
            checks_passed += 1

        # 2. Container health
        total_checks += 1
        containers_result = await self.containers.list_containers()
        if containers_result.success:
            containers = containers_result.metadata.get("containers", [])
            unhealthy = [c for c in containers if c.get("state") not in ("running", "paused")]
            if unhealthy:
                for c in unhealthy:
                    issues.append(f"CONTAINER: '{c.get('name')}' is {c.get('state')}")
            else:
                checks_passed += 1
        else:
            checks_passed += 1  # Docker not installed is ok

        # 3. Failed services
        total_checks += 1
        services_result = await self.services.failed_services()
        if services_result.success:
            if "No failed" in services_result.output or not services_result.output.strip():
                checks_passed += 1
            else:
                failed_lines = [l for l in services_result.output.splitlines() if ".service" in l]
                for line in failed_lines[:5]:
                    issues.append(f"SERVICE: {line.strip()}")
        else:
            checks_passed += 1

        # 4. Backup health
        total_checks += 1
        backup_result = await self.backups.health_check()
        if backup_result.success:
            checks_passed += 1
        else:
            backup_issues = backup_result.metadata.get("issues", [])
            issues.extend(f"BACKUP: {i}" for i in backup_issues[:3])

        # 5. Disk space
        total_checks += 1
        rc, disk_out, _ = await self._run(
            "df -h | awk '$5+0 > 85 {print $6, $5}'",
            check=False,
        )
        if disk_out:
            for line in disk_out.splitlines():
                issues.append(f"DISK: {line} usage is high")
        else:
            checks_passed += 1

        # 6. Basic network
        total_checks += 1
        net_result = await self.network.ping("1.1.1.1", count=1)
        if net_result.success:
            checks_passed += 1
        else:
            issues.append("NETWORK: Cannot reach internet (1.1.1.1 unreachable)")

        # Build report
        healthy = len(issues) == 0
        status = "HEALTHY" if healthy else f"DEGRADED ({len(issues)} issues)"

        report = f"System Health: {status}\n"
        report += f"Checks: {checks_passed}/{total_checks} passed\n"
        if issues:
            report += f"\nIssues:\n" + "\n".join(f"  ⚠ {i}" for i in issues)

        return ToolResult(
            success=healthy,
            output=report,
            metadata={
                "healthy": healthy,
                "checks_passed": checks_passed,
                "total_checks": total_checks,
                "issues": issues,
            },
        )


    # ─── Power Management ─────────────────────────────────────────────────

    async def reboot(self, delay_minutes: int = 0, message: str = "") -> ToolResult:
        """Reboot the system.

        Args:
            delay_minutes: Delay before reboot (0 = immediate).
            message: Broadcast message to logged-in users.

        Returns:
            ToolResult with reboot status.
        """
        if delay_minutes > 0:
            cmd = f"shutdown -r +{delay_minutes}"
        else:
            cmd = "shutdown -r now"

        if message:
            cmd += f' "{message}"'

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Reboot failed: {err}")

        return ToolResult(
            success=True,
            output=f"System rebooting {'now' if delay_minutes == 0 else f'in {delay_minutes} minutes'}",
            side_effects=["System reboot initiated"],
            metadata={"action": "reboot", "delay_minutes": delay_minutes},
        )

    async def shutdown(self, delay_minutes: int = 0, message: str = "") -> ToolResult:
        """Shut down the system.

        Args:
            delay_minutes: Delay before shutdown (0 = immediate).
            message: Broadcast message.

        Returns:
            ToolResult with shutdown status.
        """
        if delay_minutes > 0:
            cmd = f"shutdown +{delay_minutes}"
        else:
            cmd = "shutdown now"

        if message:
            cmd += f' "{message}"'

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Shutdown failed: {err}")

        return ToolResult(
            success=True,
            output=f"System shutting down {'now' if delay_minutes == 0 else f'in {delay_minutes} minutes'}",
            side_effects=["System shutdown initiated"],
            metadata={"action": "shutdown", "delay_minutes": delay_minutes},
        )

    async def cancel_shutdown(self) -> ToolResult:
        """Cancel a pending shutdown/reboot.

        Returns:
            ToolResult with cancellation status.
        """
        rc, out, err = await self._run("shutdown -c")
        if rc != 0:
            return ToolResult(success=False, error=f"No pending shutdown to cancel: {err}")

        return ToolResult(
            success=True,
            output="Pending shutdown/reboot cancelled",
            side_effects=["Scheduled shutdown cancelled"],
            metadata={"action": "cancel_shutdown"},
        )

    # ─── Hardware Inventory ───────────────────────────────────────────────

    async def hardware_info(self) -> ToolResult:
        """Get detailed hardware inventory.

        Returns:
            ToolResult with hardware details (CPU, RAM, disks, NICs, GPU).
        """
        hw: Dict[str, Any] = {}

        # CPU
        rc, cpu, _ = await self._run("lscpu --json 2>/dev/null || lscpu", check=False)
        hw["cpu"] = cpu

        # Memory modules
        rc, mem, _ = await self._run(
            "dmidecode -t memory 2>/dev/null | grep -A5 'Memory Device' | grep -E 'Size|Type|Speed' | head -20",
            check=False,
        )
        hw["memory_modules"] = mem or "dmidecode not available"

        # Block devices
        rc, disks, _ = await self._run(
            "lsblk -Jb -o NAME,SIZE,TYPE,MODEL,SERIAL,ROTA,TRAN",
            check=False,
        )
        hw["disks"] = disks

        # Network interfaces
        rc, nics, _ = await self._run(
            "ip -j link show | python3 -m json.tool 2>/dev/null || ip link show",
            check=False,
        )
        hw["network_interfaces"] = nics

        # GPU (if any)
        rc, gpu, _ = await self._run(
            "lspci | grep -i 'vga\\|3d\\|display'",
            check=False,
        )
        hw["gpu"] = gpu or "No dedicated GPU detected"

        # Motherboard
        rc, mb, _ = await self._run(
            "dmidecode -t baseboard 2>/dev/null | grep -E 'Manufacturer|Product' | head -2",
            check=False,
        )
        hw["motherboard"] = mb or "dmidecode not available"

        return ToolResult(
            success=True,
            output=json.dumps(hw, indent=2) if isinstance(hw, dict) else str(hw),
            metadata={"type": "hardware_inventory"},
        )

    # ─── System Updates ───────────────────────────────────────────────────

    async def check_updates(self) -> ToolResult:
        """Check for available system package updates.

        Returns:
            ToolResult with available updates.
        """
        # Try apt first (Debian/Ubuntu), then dnf (Fedora/RHEL)
        rc, out, err = await self._run(
            "apt list --upgradable 2>/dev/null", check=False
        )
        if rc == 0 and "upgradable" in out.lower():
            return ToolResult(
                success=True,
                output=out,
                metadata={"package_manager": "apt"},
            )

        rc, out, err = await self._run(
            "dnf check-update 2>/dev/null", check=False
        )
        if out:
            return ToolResult(
                success=True,
                output=out,
                metadata={"package_manager": "dnf"},
            )

        return ToolResult(
            success=True,
            output="System is up to date (or package manager not detected)",
            metadata={"package_manager": "unknown"},
        )

    async def apply_updates(self, reboot_if_needed: bool = False) -> ToolResult:
        """Apply all available system updates.

        Args:
            reboot_if_needed: Automatically reboot if kernel was updated.

        Returns:
            ToolResult with update results.
        """
        # Try apt
        rc, out, err = await self._run(
            "apt-get update && apt-get upgrade -y 2>/dev/null",
            check=False,
        )
        if rc == 0:
            result_output = out
            pkg_mgr = "apt"
        else:
            # Try dnf
            rc, out, err = await self._run(
                "dnf upgrade -y 2>/dev/null", check=False
            )
            result_output = out
            pkg_mgr = "dnf"

        if rc != 0:
            return ToolResult(success=False, error=f"Update failed: {err}")

        side_effects = ["System packages updated"]

        # Check if reboot needed
        reboot_needed = False
        if pkg_mgr == "apt":
            rc2, reboot_check, _ = await self._run(
                "test -f /var/run/reboot-required && echo yes || echo no",
                check=False,
            )
            reboot_needed = reboot_check.strip() == "yes"
        elif pkg_mgr == "dnf":
            rc2, needs, _ = await self._run(
                "needs-restarting -r 2>/dev/null; echo $?", check=False
            )
            reboot_needed = "1" in needs

        if reboot_needed:
            if reboot_if_needed:
                side_effects.append("System will reboot")
                await self.reboot(delay_minutes=1, message="MK: Rebooting after updates")
            else:
                side_effects.append("REBOOT RECOMMENDED (kernel updated)")

        return ToolResult(
            success=True,
            output=f"Updates applied ({pkg_mgr})\n{result_output[-500:] if len(result_output) > 500 else result_output}",
            side_effects=side_effects,
            metadata={"package_manager": pkg_mgr, "reboot_needed": reboot_needed},
        )

    # ─── Quick Actions ────────────────────────────────────────────────────

    async def quick_deploy_app(
        self,
        app_name: str,
        image: str,
        ports: Optional[Dict[str, str]] = None,
        volumes: Optional[list] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ToolResult:
        """Quick deploy an app as a Docker container with sensible defaults.

        This is the "one command" deploy — MK's equivalent of clicking
        install in a home server app store.

        Args:
            app_name: Name for the container.
            image: Docker image.
            ports: Port mappings.
            volumes: Volume mounts.
            env: Environment variables.

        Returns:
            ToolResult with deployment status.
        """
        return await self.containers.run_container(
            image=image,
            name=app_name,
            ports=ports,
            volumes=volumes,
            environment=env,
            restart_policy="unless-stopped",
            labels={"mk.managed": "true", "mk.app": app_name},
        )
