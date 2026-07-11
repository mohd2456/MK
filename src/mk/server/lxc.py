"""LXC Manager - Lightweight system containers via lxc-* tools.

Wraps the open-source LXC toolchain (lxc-create, lxc-start, etc.)
for system containers. These are lighter than VMs but heavier than
Docker — they run a full init system (systemd/openrc) inside.

Good for: running a full OS (Ubuntu, Alpine, Debian) as a container
without the overhead of QEMU/KVM. Same concept as Proxmox CT.

Tools used:
    lxc-create   - Create containers from templates/images
    lxc-start    - Start containers
    lxc-stop     - Stop containers
    lxc-attach   - Run commands inside containers
    lxc-info     - Container status
    lxc-ls       - List containers
    lxc-destroy  - Remove containers
    lxc-snapshot - Snapshot containers
    lxc-copy     - Clone containers
"""

from __future__ import annotations

import logging

from mk.tools.base import ToolResult
from ._shell import safe_quote, validate_name
from ._run import run_cmd

logger = logging.getLogger(__name__)


class LXCManager:
    """Manages LXC system containers via the lxc-* CLI tools."""

    # --- Lifecycle ---

    async def list_containers(self) -> ToolResult:
        """List all LXC containers with status."""
        rc, out, err = await run_cmd("lxc-ls --fancy")
        if rc != 0:
            return ToolResult(success=False, error=f"LXC not available: {err}")
        return ToolResult(success=True, output=out if out else "No LXC containers")

    async def container_info(self, name: str) -> ToolResult:
        """Get info about an LXC container."""
        validate_name(name, "container name")
        rc, out, err = await run_cmd(f"lxc-info --name {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Container '{name}' not found: {err}")
        return ToolResult(success=True, output=out, metadata={"container": name})

    async def create_container(
        self,
        name: str,
        distro: str = "alpine",
        release: str = "3.19",
        arch: str = "amd64",
        autostart: bool = False,
    ) -> ToolResult:
        """Create an LXC container from the download template.

        Args:
            name: Container name.
            distro: Distribution (alpine, ubuntu, debian, fedora, etc.).
            release: Release version.
            arch: Architecture (amd64, arm64).
            autostart: Start on host boot.
        """
        validate_name(name, "container name")

        rc, out, err = await run_cmd(
            f"lxc-create --name {safe_quote(name)} --template download "
            f"-- --dist {safe_quote(distro)} --release {safe_quote(release)} --arch {safe_quote(arch)}",
            timeout=300,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create container: {err}")

        if autostart:
            config_path = f"/var/lib/lxc/{name}/config"
            await run_cmd(f"bash -c 'echo \"lxc.start.auto = 1\" >> {safe_quote(config_path)}'")

        return ToolResult(
            success=True,
            output=f"LXC container '{name}' created ({distro} {release} {arch})",
            side_effects=[f"Container '{name}' ready to start"],
            metadata={"container": name, "distro": distro, "release": release},
        )

    async def start_container(self, name: str) -> ToolResult:
        """Start an LXC container."""
        validate_name(name, "container name")
        rc, out, err = await run_cmd(f"lxc-start --name {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start '{name}': {err}")
        return ToolResult(
            success=True,
            output=f"Container '{name}' started",
            side_effects=[f"LXC container '{name}' running"],
        )

    async def stop_container(self, name: str, force: bool = False) -> ToolResult:
        """Stop an LXC container."""
        validate_name(name, "container name")
        kill_flag = "--kill" if force else ""
        rc, out, err = await run_cmd(f"lxc-stop --name {safe_quote(name)} {kill_flag}".strip())
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to stop '{name}': {err}")
        return ToolResult(success=True, output=f"Container '{name}' stopped")

    async def restart_container(self, name: str) -> ToolResult:
        """Restart an LXC container."""
        validate_name(name, "container name")
        await run_cmd(f"lxc-stop --name {safe_quote(name)}")
        rc, out, err = await run_cmd(f"lxc-start --name {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to restart '{name}': {err}")
        return ToolResult(success=True, output=f"Container '{name}' restarted")

    async def destroy_container(self, name: str) -> ToolResult:
        """Destroy an LXC container permanently."""
        validate_name(name, "container name")
        # Stop first if running
        await run_cmd(f"lxc-stop --name {safe_quote(name)}", sudo=True)
        rc, out, err = await run_cmd(f"lxc-destroy --name {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy '{name}': {err}")
        return ToolResult(
            success=True,
            output=f"Container '{name}' destroyed",
            side_effects=[f"Container '{name}' permanently removed"],
        )

    # --- Execute inside container ---

    async def exec_command(self, name: str, command: str) -> ToolResult:
        """Run a command inside an LXC container.

        Args:
            name: Container name.
            command: Command to execute inside.
        """
        validate_name(name, "container name")
        rc, out, err = await run_cmd(
            f"lxc-attach --name {safe_quote(name)} --clear-env -- {command}",
            timeout=60,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Command failed in '{name}': {err}")
        return ToolResult(success=True, output=out, metadata={"container": name})

    # --- Snapshots ---

    async def list_snapshots(self, name: str) -> ToolResult:
        """List snapshots for a container."""
        validate_name(name, "container name")
        rc, out, err = await run_cmd(f"lxc-snapshot --name {safe_quote(name)} --list")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list snapshots: {err}")
        return ToolResult(success=True, output=out if out else "No snapshots")

    async def create_snapshot(self, name: str) -> ToolResult:
        """Create a snapshot of a container."""
        validate_name(name, "container name")
        rc, out, err = await run_cmd(f"lxc-snapshot --name {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Snapshot failed: {err}")
        return ToolResult(
            success=True,
            output=f"Snapshot created for '{name}'",
            side_effects=["LXC snapshot created"],
        )

    async def restore_snapshot(self, name: str, snap_name: str) -> ToolResult:
        """Restore a container from a snapshot."""
        validate_name(name, "container name")
        validate_name(snap_name, "snapshot name")
        rc, out, err = await run_cmd(
            f"lxc-snapshot --name {safe_quote(name)} --restore {safe_quote(snap_name)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Restore failed: {err}")
        return ToolResult(success=True, output=f"Container '{name}' restored to '{snap_name}'")

    # --- Clone ---

    async def clone_container(self, source: str, new_name: str) -> ToolResult:
        """Clone a container."""
        validate_name(source, "source container")
        validate_name(new_name, "new container name")
        rc, out, err = await run_cmd(
            f"lxc-copy --name {safe_quote(source)} --newname {safe_quote(new_name)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Clone failed: {err}")
        return ToolResult(
            success=True,
            output=f"Container '{source}' cloned to '{new_name}'",
            side_effects=[f"New container '{new_name}' created"],
        )

    # --- Configuration ---

    async def set_autostart(self, name: str, enabled: bool = True) -> ToolResult:
        """Set container autostart."""
        validate_name(name, "container name")
        config_path = f"/var/lib/lxc/{name}/config"
        value = "1" if enabled else "0"

        # Remove existing autostart line and add new one
        await run_cmd(f"sed -i '/lxc.start.auto/d' {safe_quote(config_path)}")
        await run_cmd(f"bash -c 'echo \"lxc.start.auto = {value}\" >> {safe_quote(config_path)}'")

        state = "enabled" if enabled else "disabled"
        return ToolResult(success=True, output=f"Autostart {state} for '{name}'")

    async def set_memory_limit(self, name: str, limit_mb: int) -> ToolResult:
        """Set memory limit on a container."""
        validate_name(name, "container name")
        config_path = f"/var/lib/lxc/{name}/config"
        limit_bytes = limit_mb * 1024 * 1024

        await run_cmd(f"sed -i '/lxc.cgroup2.memory.max/d' {safe_quote(config_path)}")
        await run_cmd(
            f"bash -c 'echo \"lxc.cgroup2.memory.max = {limit_bytes}\" >> {safe_quote(config_path)}'"
        )
        return ToolResult(success=True, output=f"Memory limit set to {limit_mb}MB for '{name}'")

    async def set_cpu_limit(self, name: str, cpus: int) -> ToolResult:
        """Set CPU core limit on a container."""
        validate_name(name, "container name")
        config_path = f"/var/lib/lxc/{name}/config"
        # CPU quota: 100000 per core
        quota = cpus * 100000

        await run_cmd(f"sed -i '/lxc.cgroup2.cpu.max/d' {safe_quote(config_path)}")
        await run_cmd(
            f"bash -c 'echo \"lxc.cgroup2.cpu.max = {quota} 100000\" >> {safe_quote(config_path)}'"
        )
        return ToolResult(success=True, output=f"CPU limit set to {cpus} cores for '{name}'")

    async def add_mount(self, name: str, host_path: str, container_path: str) -> ToolResult:
        """Add a bind mount to a container.

        Args:
            name: Container name.
            host_path: Path on the host.
            container_path: Path inside container (relative, no leading /).
        """
        validate_name(name, "container name")
        config_path = f"/var/lib/lxc/{name}/config"
        # LXC mount entries use relative paths (no leading /)
        rel_path = container_path.lstrip("/")
        mount_entry = f"{host_path} {rel_path} none bind,create=dir 0 0"

        await run_cmd(
            f"bash -c 'echo \"lxc.mount.entry = {mount_entry}\" >> {safe_quote(config_path)}'"
        )
        return ToolResult(
            success=True,
            output=f"Mount added: {host_path} -> /{rel_path} in '{name}'",
            side_effects=["Restart container to apply mount"],
        )
