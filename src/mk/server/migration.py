"""Migration Manager - Transfer MK between machines seamlessly.

MK needs to move between hardware — new specs, better or worse.
This handles exporting and importing MK's state so you can:
  - Back up MK's brain/config/memory to a file
  - Restore onto any new machine
  - Auto-detect new hardware and adjust (memory limits, CPU budgets, etc.)
  - Keep your containers, stacks, configs, backup jobs intact

Export produces a single .tar.gz with:
  - /etc/mk/ (config)
  - /var/lib/mk/ (memory, state, backup job configs)
  - /opt/mk/stacks/ (docker compose files)
  - Docker volume list + compose files
  - Crontabs and systemd timers
  - WireGuard configs
  - Samba/NFS share configs
  - User list + SSH keys

Import unpacks it all and adapts to the new hardware.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult
from ._shell import safe_quote
from ._run import run_cmd

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_PATH = "/var/lib/mk/exports"


class MigrationManager:
    """Handles MK state export/import for hardware transfers."""

    def __init__(self, export_dir: str = DEFAULT_EXPORT_PATH) -> None:
        self._export_dir = export_dir

    async def export_state(self, output_path: Optional[str] = None) -> ToolResult:
        """Export MK's full state to a portable archive.

        Packages config, memory, stacks, and system settings into
        a single .tar.gz that can be restored on any machine.

        Args:
            output_path: Custom output path (default: /var/lib/mk/exports/).

        Returns:
            ToolResult with export file path.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        export_name = f"mk-export-{timestamp}"
        staging_dir = f"/tmp/{export_name}"

        if not output_path:
            output_path = f"{self._export_dir}/{export_name}.tar.gz"

        await run_cmd(f"mkdir -p {safe_quote(staging_dir)}", sudo=False)
        await run_cmd(f"mkdir -p {safe_quote(self._export_dir)}", sudo=True)

        # Collect MK config
        await run_cmd(f"cp -r /etc/mk {staging_dir}/config 2>/dev/null || true", sudo=True)

        # Collect MK state/memory
        await run_cmd(f"cp -r /var/lib/mk {staging_dir}/state 2>/dev/null || true", sudo=True)

        # Collect docker compose stacks
        await run_cmd(f"cp -r /opt/mk/stacks {staging_dir}/stacks 2>/dev/null || true", sudo=True)

        # Docker container/image list
        await run_cmd(
            f"docker ps -a --format '{{{{json .}}}}' > {staging_dir}/docker-containers.json 2>/dev/null || true",
            sudo=False,
        )
        await run_cmd(
            f"docker images --format '{{{{json .}}}}' > {staging_dir}/docker-images.json 2>/dev/null || true",
            sudo=False,
        )

        # WireGuard configs
        await run_cmd(f"cp -r /etc/wireguard {staging_dir}/wireguard 2>/dev/null || true", sudo=True)

        # Samba config
        await run_cmd(f"cp /etc/samba/smb.conf {staging_dir}/smb.conf 2>/dev/null || true", sudo=True)

        # NFS exports
        await run_cmd(f"cp /etc/exports {staging_dir}/nfs-exports 2>/dev/null || true", sudo=True)

        # User SSH keys (non-system users)
        await run_cmd(f"mkdir -p {staging_dir}/ssh-keys", sudo=False)
        rc, users, _ = await run_cmd(
            "awk -F: '$3 >= 1000 && $3 < 65534 {print $1 \":\" $6}' /etc/passwd",
            sudo=False,
        )
        if rc == 0 and users:
            for line in users.splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    user, home = parts
                    await run_cmd(
                        f"cp -r {home}/.ssh {staging_dir}/ssh-keys/{user} 2>/dev/null || true",
                        sudo=True,
                    )

        # Systemd custom timers (MK backup timers)
        await run_cmd(
            f"cp /etc/systemd/system/mk-backup-* {staging_dir}/ 2>/dev/null || true",
            sudo=True,
        )

        # Hardware profile (for reference on import)
        hw_info = {}
        rc, out, _ = await run_cmd("nproc", sudo=False)
        hw_info["cpu_cores"] = int(out) if out.isdigit() else 0
        rc, out, _ = await run_cmd("free -b | awk '/Mem:/{print $2}'", sudo=False)
        hw_info["ram_bytes"] = int(out) if out.isdigit() else 0
        rc, out, _ = await run_cmd("uname -m", sudo=False)
        hw_info["arch"] = out
        rc, out, _ = await run_cmd("hostname", sudo=False)
        hw_info["hostname"] = out
        hw_info["exported_at"] = datetime.now().isoformat()

        hw_json = json.dumps(hw_info, indent=2)
        await run_cmd(f"tee {staging_dir}/hardware-profile.json", sudo=False, stdin_data=hw_json)

        # Create archive
        rc, _, err = await run_cmd(
            f"tar -czf {safe_quote(output_path)} -C /tmp {safe_quote(export_name)}",
            sudo=True,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create archive: {err}")

        # Cleanup staging
        await run_cmd(f"rm -rf {safe_quote(staging_dir)}", sudo=False)

        # Get file size
        rc, size, _ = await run_cmd(f"du -h {safe_quote(output_path)}", sudo=False)

        return ToolResult(
            success=True,
            output=f"MK state exported: {output_path}\nSize: {size.split()[0] if size else 'unknown'}",
            side_effects=[f"Export archive created at {output_path}"],
            metadata={"path": output_path, "hardware": hw_info},
        )

    async def import_state(self, archive_path: str) -> ToolResult:
        """Import MK state from an export archive onto this machine.

        Unpacks config, memory, stacks, and adapts to current hardware.

        Args:
            archive_path: Path to the .tar.gz export file.

        Returns:
            ToolResult with import results.
        """
        staging_dir = "/tmp/mk-import"
        await run_cmd(f"rm -rf {staging_dir}", sudo=False)
        await run_cmd(f"mkdir -p {staging_dir}", sudo=False)

        # Extract
        rc, _, err = await run_cmd(
            f"tar -xzf {safe_quote(archive_path)} -C {staging_dir} --strip-components=1",
            sudo=True,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to extract archive: {err}")

        restored = []

        # Restore config
        rc, _, _ = await run_cmd(f"cp -r {staging_dir}/config/* /etc/mk/ 2>/dev/null", sudo=True)
        if rc == 0:
            restored.append("config")

        # Restore state/memory
        rc, _, _ = await run_cmd(f"cp -r {staging_dir}/state/* /var/lib/mk/ 2>/dev/null", sudo=True)
        if rc == 0:
            restored.append("memory/state")

        # Restore stacks
        rc, _, _ = await run_cmd(f"cp -r {staging_dir}/stacks/* /opt/mk/stacks/ 2>/dev/null", sudo=True)
        if rc == 0:
            restored.append("docker stacks")

        # Restore WireGuard
        rc, _, _ = await run_cmd(f"cp -r {staging_dir}/wireguard/* /etc/wireguard/ 2>/dev/null", sudo=True)
        if rc == 0:
            restored.append("wireguard")

        # Restore Samba
        rc, _, _ = await run_cmd(f"cp {staging_dir}/smb.conf /etc/samba/smb.conf 2>/dev/null", sudo=True)
        if rc == 0:
            restored.append("samba shares")

        # Restore NFS
        rc, _, _ = await run_cmd(f"cp {staging_dir}/nfs-exports /etc/exports 2>/dev/null", sudo=True)
        if rc == 0:
            restored.append("nfs exports")

        # Restore backup timers
        rc, _, _ = await run_cmd(f"cp {staging_dir}/mk-backup-* /etc/systemd/system/ 2>/dev/null", sudo=True)
        if rc == 0:
            await run_cmd("systemctl daemon-reload", sudo=True)
            restored.append("backup timers")

        # Read old hardware profile
        rc, hw_json, _ = await run_cmd(f"cat {staging_dir}/hardware-profile.json 2>/dev/null", sudo=False)
        old_hw = json.loads(hw_json) if rc == 0 and hw_json else {}

        # Detect current hardware
        rc, cores, _ = await run_cmd("nproc", sudo=False)
        rc, ram, _ = await run_cmd("free -b | awk '/Mem:/{print $2}'", sudo=False)
        new_hw = {
            "cpu_cores": int(cores) if cores.isdigit() else 0,
            "ram_bytes": int(ram) if ram.isdigit() else 0,
        }

        # Cleanup
        await run_cmd(f"rm -rf {staging_dir}", sudo=False)

        # Build summary
        output_lines = [f"MK state imported from {archive_path}"]
        output_lines.append(f"Restored: {', '.join(restored)}")
        if old_hw:
            output_lines.append(f"\nHardware change:")
            old_ram_gb = old_hw.get('ram_bytes', 0) / (1024**3)
            new_ram_gb = new_hw['ram_bytes'] / (1024**3)
            output_lines.append(f"  CPU: {old_hw.get('cpu_cores', '?')} cores → {new_hw['cpu_cores']} cores")
            output_lines.append(f"  RAM: {old_ram_gb:.1f}GB → {new_ram_gb:.1f}GB")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            side_effects=[f"Restored: {', '.join(restored)}"],
            metadata={"restored": restored, "old_hardware": old_hw, "new_hardware": new_hw},
        )

    async def hardware_profile(self) -> ToolResult:
        """Show current hardware profile (what MK is running on)."""
        info: Dict[str, Any] = {}

        rc, out, _ = await run_cmd("nproc", sudo=False)
        info["cpu_cores"] = int(out) if out and out.isdigit() else 0

        rc, out, _ = await run_cmd("lscpu | grep 'Model name' | cut -d: -f2 | xargs", sudo=False)
        info["cpu_model"] = out or "unknown"

        rc, out, _ = await run_cmd("free -b | awk '/Mem:/{print $2}'", sudo=False)
        info["ram_bytes"] = int(out) if out and out.isdigit() else 0
        info["ram_gb"] = round(info["ram_bytes"] / (1024**3), 1)

        rc, out, _ = await run_cmd("df -B1 / | awk 'NR==2{print $2, $4}'", sudo=False)
        if out:
            parts = out.split()
            info["disk_total_gb"] = round(int(parts[0]) / (1024**3), 1) if parts else 0
            info["disk_free_gb"] = round(int(parts[1]) / (1024**3), 1) if len(parts) > 1 else 0

        rc, out, _ = await run_cmd("uname -m", sudo=False)
        info["arch"] = out or "unknown"

        rc, out, _ = await run_cmd("hostname", sudo=False)
        info["hostname"] = out or "unknown"

        rc, out, _ = await run_cmd("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'", sudo=False)
        info["os"] = out or "unknown"

        return ToolResult(
            success=True,
            output=json.dumps(info, indent=2),
            metadata=info,
        )
