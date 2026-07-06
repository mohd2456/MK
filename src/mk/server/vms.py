"""VM Manager - KVM/QEMU virtual machines via libvirt.

Wraps the open-source libvirt/virsh toolchain for full VM lifecycle.
MK doesn't reinvent virtualization — it talks to libvirt, the same
backend Proxmox, oVirt, and OpenStack use.

Tools used:
    virsh       - VM lifecycle (start, stop, snapshot, migrate)
    virt-install - VM creation with cloud-init
    qemu-img    - Disk image creation/conversion/resize

Capabilities:
    - Create VMs from ISO or cloud images (cloud-init for zero-touch setup)
    - Start, stop, reboot, pause, resume VMs
    - Snapshots (create, list, revert, delete)
    - Resource management (vCPU, RAM hot-add)
    - Disk management (add, resize, detach)
    - Console access info
    - VM cloning
    - List and manage storage pools for VM disks
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult
from ._shell import safe_quote, validate_name
from ._run import run_cmd

logger = logging.getLogger(__name__)


class VMManager:
    """Manages KVM/QEMU virtual machines through libvirt (virsh).

    All operations shell out to virsh/virt-install/qemu-img.
    These are the same tools Proxmox uses under the hood.
    """

    def __init__(self, connect_uri: str = "qemu:///system") -> None:
        """Initialize VM Manager.

        Args:
            connect_uri: Libvirt connection URI.
        """
        self._uri = connect_uri
        self._virsh = f"virsh -c {safe_quote(connect_uri)}"

    async def _virsh_cmd(self, subcmd: str) -> Tuple[int, str, str]:
        """Run a virsh subcommand."""
        return await run_cmd(f"{self._virsh} {subcmd}")

    # --- VM Lifecycle ---

    async def list_vms(self, all_states: bool = True) -> ToolResult:
        """List all virtual machines."""
        flag = "--all" if all_states else ""
        rc, out, err = await self._virsh_cmd(f"list {flag}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list VMs: {err}")
        return ToolResult(success=True, output=out)

    async def vm_info(self, name: str) -> ToolResult:
        """Get detailed info about a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"dominfo {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"VM '{name}' not found: {err}")
        return ToolResult(success=True, output=out, metadata={"vm": name})

    async def start_vm(self, name: str) -> ToolResult:
        """Start a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"start {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start '{name}': {err}")
        return ToolResult(
            success=True,
            output=f"VM '{name}' started",
            side_effects=[f"VM '{name}' is now running"],
        )

    async def stop_vm(self, name: str, force: bool = False) -> ToolResult:
        """Stop a VM (graceful shutdown or force off)."""
        validate_name(name, "VM name")
        cmd = "destroy" if force else "shutdown"
        rc, out, err = await self._virsh_cmd(f"{cmd} {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to stop '{name}': {err}")
        method = "forced off" if force else "graceful shutdown"
        return ToolResult(
            success=True,
            output=f"VM '{name}' {method}",
            side_effects=[f"VM '{name}' stopped"],
        )

    async def reboot_vm(self, name: str) -> ToolResult:
        """Reboot a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"reboot {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to reboot '{name}': {err}")
        return ToolResult(success=True, output=f"VM '{name}' rebooting")

    async def pause_vm(self, name: str) -> ToolResult:
        """Pause (suspend) a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"suspend {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to pause '{name}': {err}")
        return ToolResult(success=True, output=f"VM '{name}' paused")

    async def resume_vm(self, name: str) -> ToolResult:
        """Resume a paused VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"resume {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to resume '{name}': {err}")
        return ToolResult(success=True, output=f"VM '{name}' resumed")

    async def delete_vm(self, name: str, remove_storage: bool = False) -> ToolResult:
        """Delete a VM definition (must be stopped first)."""
        validate_name(name, "VM name")
        flags = "--remove-all-storage" if remove_storage else ""
        rc, out, err = await self._virsh_cmd(f"undefine {safe_quote(name)} {flags}".strip())
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to delete '{name}': {err}")
        return ToolResult(
            success=True,
            output=f"VM '{name}' deleted",
            side_effects=[f"VM '{name}' undefined" + (", storage removed" if remove_storage else "")],
        )

    # --- VM Creation ---

    async def create_vm(
        self,
        name: str,
        ram_mb: int = 2048,
        vcpus: int = 2,
        disk_size_gb: int = 20,
        os_variant: str = "generic",
        iso_path: Optional[str] = None,
        cloud_image: Optional[str] = None,
        network: str = "default",
        autostart: bool = False,
    ) -> ToolResult:
        """Create a new VM using virt-install.

        Either provide iso_path for manual install, or cloud_image
        for automatic cloud-init provisioning.

        Args:
            name: VM name.
            ram_mb: RAM in megabytes.
            vcpus: Number of virtual CPUs.
            disk_size_gb: Disk size in GB.
            os_variant: OS variant hint (e.g., ubuntu22.04, debian12).
            iso_path: Path to ISO for manual install.
            cloud_image: Path to cloud image (qcow2) for cloud-init.
            network: Libvirt network name.
            autostart: Auto-start on host boot.
        """
        validate_name(name, "VM name")

        cmd_parts = [
            "virt-install",
            f"--name {safe_quote(name)}",
            f"--ram {ram_mb}",
            f"--vcpus {vcpus}",
            f"--os-variant {safe_quote(os_variant)}",
            f"--network network={safe_quote(network)}",
            "--noautoconsole",
        ]

        if cloud_image:
            # Cloud image: copy it as the VM disk and use cloud-init
            disk_path = f"/var/lib/libvirt/images/{name}.qcow2"
            # Copy and resize the cloud image
            rc, _, err = await run_cmd(
                f"cp {safe_quote(cloud_image)} {safe_quote(disk_path)}"
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Failed to copy cloud image: {err}")

            rc, _, err = await run_cmd(
                f"qemu-img resize {safe_quote(disk_path)} {disk_size_gb}G"
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Failed to resize disk: {err}")

            cmd_parts.append(f"--disk path={safe_quote(disk_path)},format=qcow2")
            cmd_parts.append("--import")
            cmd_parts.append("--cloud-init")
        elif iso_path:
            # ISO install
            disk_path = f"/var/lib/libvirt/images/{name}.qcow2"
            cmd_parts.append(
                f"--disk path={safe_quote(disk_path)},size={disk_size_gb},format=qcow2"
            )
            cmd_parts.append(f"--cdrom {safe_quote(iso_path)}")
        else:
            return ToolResult(
                success=False,
                error="Either iso_path or cloud_image is required",
            )

        cmd = " ".join(cmd_parts)
        rc, out, err = await run_cmd(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create VM: {err}")

        # Set autostart if requested
        if autostart:
            await self._virsh_cmd(f"autostart {safe_quote(name)}")

        return ToolResult(
            success=True,
            output=f"VM '{name}' created ({vcpus} vCPU, {ram_mb}MB RAM, {disk_size_gb}GB disk)",
            side_effects=[f"VM '{name}' created and started"],
            metadata={"vm": name, "ram_mb": ram_mb, "vcpus": vcpus, "disk_gb": disk_size_gb},
        )

    # --- Snapshots ---

    async def list_snapshots(self, name: str) -> ToolResult:
        """List snapshots for a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"snapshot-list {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list snapshots: {err}")
        return ToolResult(success=True, output=out, metadata={"vm": name})

    async def create_snapshot(self, name: str, snap_name: Optional[str] = None, description: str = "") -> ToolResult:
        """Create a VM snapshot."""
        validate_name(name, "VM name")
        if snap_name:
            validate_name(snap_name, "snapshot name")

        desc_flag = f"--description {safe_quote(description)}" if description else ""
        name_flag = f"--name {safe_quote(snap_name)}" if snap_name else ""

        rc, out, err = await self._virsh_cmd(
            f"snapshot-create-as {safe_quote(name)} {name_flag} {desc_flag}".strip()
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Snapshot failed: {err}")
        return ToolResult(
            success=True,
            output=f"Snapshot created for VM '{name}'",
            side_effects=[f"VM snapshot created"],
        )

    async def revert_snapshot(self, name: str, snap_name: str) -> ToolResult:
        """Revert a VM to a snapshot."""
        validate_name(name, "VM name")
        validate_name(snap_name, "snapshot name")
        rc, out, err = await self._virsh_cmd(
            f"snapshot-revert {safe_quote(name)} {safe_quote(snap_name)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Revert failed: {err}")
        return ToolResult(
            success=True,
            output=f"VM '{name}' reverted to snapshot '{snap_name}'",
            side_effects=[f"VM state rolled back"],
        )

    async def delete_snapshot(self, name: str, snap_name: str) -> ToolResult:
        """Delete a VM snapshot."""
        validate_name(name, "VM name")
        validate_name(snap_name, "snapshot name")
        rc, out, err = await self._virsh_cmd(
            f"snapshot-delete {safe_quote(name)} {safe_quote(snap_name)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Delete snapshot failed: {err}")
        return ToolResult(success=True, output=f"Snapshot '{snap_name}' deleted")

    # --- Resources ---

    async def set_vcpus(self, name: str, count: int) -> ToolResult:
        """Set vCPU count for a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(
            f"setvcpus {safe_quote(name)} {count} --config --maximum"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set vCPUs: {err}")
        return ToolResult(success=True, output=f"VM '{name}' set to {count} vCPUs")

    async def set_memory(self, name: str, ram_mb: int) -> ToolResult:
        """Set RAM for a VM (requires restart)."""
        validate_name(name, "VM name")
        # Convert to KB for virsh
        ram_kb = ram_mb * 1024
        rc, out, err = await self._virsh_cmd(
            f"setmaxmem {safe_quote(name)} {ram_kb} --config"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set memory: {err}")
        await self._virsh_cmd(f"setmem {safe_quote(name)} {ram_kb} --config")
        return ToolResult(success=True, output=f"VM '{name}' set to {ram_mb}MB RAM (restart to apply)")

    async def add_disk(self, name: str, size_gb: int, target: str = "vdb") -> ToolResult:
        """Add a new disk to a VM."""
        validate_name(name, "VM name")
        disk_path = f"/var/lib/libvirt/images/{name}-{target}.qcow2"

        # Create the disk image
        rc, _, err = await run_cmd(f"qemu-img create -f qcow2 {safe_quote(disk_path)} {size_gb}G")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create disk: {err}")

        # Attach to VM
        rc, _, err = await self._virsh_cmd(
            f"attach-disk {safe_quote(name)} {safe_quote(disk_path)} {safe_quote(target)} "
            f"--driver qemu --subdriver qcow2 --persistent"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to attach disk: {err}")

        return ToolResult(
            success=True,
            output=f"Added {size_gb}GB disk to '{name}' as {target}",
            side_effects=[f"Disk image created at {disk_path}"],
        )

    # --- Clone ---

    async def clone_vm(self, source: str, new_name: str) -> ToolResult:
        """Clone a VM (must be stopped)."""
        validate_name(source, "source VM")
        validate_name(new_name, "new VM name")
        rc, out, err = await run_cmd(
            f"virt-clone --original {safe_quote(source)} --name {safe_quote(new_name)} --auto-clone"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Clone failed: {err}")
        return ToolResult(
            success=True,
            output=f"VM '{source}' cloned to '{new_name}'",
            side_effects=[f"New VM '{new_name}' created as clone"],
        )

    # --- Console ---

    async def console_info(self, name: str) -> ToolResult:
        """Get VNC/SPICE console connection info for a VM."""
        validate_name(name, "VM name")
        rc, out, err = await self._virsh_cmd(f"domdisplay {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"No console available: {err}")
        return ToolResult(success=True, output=f"Console: {out}", metadata={"vm": name, "display": out})

    # --- Autostart ---

    async def set_autostart(self, name: str, enabled: bool = True) -> ToolResult:
        """Set VM autostart on host boot."""
        validate_name(name, "VM name")
        flag = "--disable" if not enabled else ""
        rc, out, err = await self._virsh_cmd(f"autostart {flag} {safe_quote(name)}".strip())
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set autostart: {err}")
        state = "enabled" if enabled else "disabled"
        return ToolResult(success=True, output=f"Autostart {state} for '{name}'")
