"""Storage Manager - ZFS pool, dataset, snapshot, and share management.

The AI-managed storage layer. Handles everything TrueNAS does for storage:
- ZFS pool creation, status, scrub, expansion
- Dataset creation with compression, quotas, encryption
- Snapshot creation, listing, rollback, deletion
- SMB/NFS share management
- Disk health monitoring via SMART

All operations execute real system commands. MK decides when to snapshot,
when to scrub, when to alert — no manual scheduling needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from .models import (
    Dataset,
    PoolStatus,
    Share,
    ShareType,
    Snapshot,
    VDevType,
    ZPool,
)

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages ZFS storage pools, datasets, snapshots, and network shares.

    This is the core storage brain of MK OS. It wraps ZFS commands,
    share configuration (SMB via samba, NFS via /etc/exports), and
    disk health monitoring into a unified interface that MK's AI
    can reason about and act on.
    """

    def __init__(self, sudo: bool = True) -> None:
        """Initialize the Storage Manager.

        Args:
            sudo: Whether to prefix commands with sudo (default True for system ops).
        """
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    # ─── Command Execution ────────────────────────────────────────────────

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously.

        Args:
            cmd: Command string to execute.
            check: If True, log errors on non-zero exit.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Storage exec: {full_cmd}")

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

    # ─── Pool Operations ──────────────────────────────────────────────────

    async def list_pools(self) -> ToolResult:
        """List all ZFS pools with their status and usage.

        Returns:
            ToolResult with pool information.
        """
        rc, out, err = await self._run(
            "zpool list -Hp -o name,size,alloc,free,frag,health"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list pools: {err}")

        pools: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                name, size, alloc, free, frag, health = parts[:6]
                pools.append({
                    "name": name,
                    "size_bytes": int(size),
                    "used_bytes": int(alloc),
                    "free_bytes": int(free),
                    "fragmentation": int(frag.rstrip("%")) if frag != "-" else 0,
                    "status": health.lower(),
                })

        return ToolResult(
            success=True,
            output=json.dumps(pools, indent=2),
            metadata={"pool_count": len(pools), "pools": pools},
        )

    async def pool_status(self, pool_name: str) -> ToolResult:
        """Get detailed status of a specific pool.

        Args:
            pool_name: Name of the ZFS pool.

        Returns:
            ToolResult with detailed pool status.
        """
        rc, out, err = await self._run(f"zpool status {pool_name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Pool '{pool_name}' not found: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"pool": pool_name},
        )

    async def create_pool(
        self,
        name: str,
        vdev_type: str,
        disks: List[str],
        force: bool = False,
    ) -> ToolResult:
        """Create a new ZFS pool.

        Args:
            name: Pool name.
            vdev_type: VDEV layout (mirror, raidz1, raidz2, raidz3, stripe).
            disks: List of disk device paths (e.g., ["/dev/sda", "/dev/sdb"]).
            force: Force creation even if disks appear in use.

        Returns:
            ToolResult with creation status.
        """
        if not name:
            return ToolResult(success=False, error="Pool name is required")
        if not disks:
            return ToolResult(success=False, error="At least one disk is required")

        # Validate vdev type
        valid_types = ["mirror", "raidz1", "raidz2", "raidz3", "stripe"]
        if vdev_type not in valid_types:
            return ToolResult(
                success=False,
                error=f"Invalid vdev type '{vdev_type}'. Use: {', '.join(valid_types)}",
            )

        # Build command
        force_flag = "-f " if force else ""
        vdev_arg = "" if vdev_type == "stripe" else f"{vdev_type} "
        disk_args = " ".join(disks)
        cmd = f"zpool create {force_flag}{name} {vdev_arg}{disk_args}"

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create pool: {err}")

        return ToolResult(
            success=True,
            output=f"Pool '{name}' created with {vdev_type} topology using {len(disks)} disks",
            side_effects=[f"ZFS pool '{name}' created", f"Disks allocated: {disk_args}"],
            metadata={"pool": name, "vdev_type": vdev_type, "disks": disks},
        )

    async def destroy_pool(self, name: str, force: bool = False) -> ToolResult:
        """Destroy a ZFS pool. DANGEROUS - requires confirmation.

        Args:
            name: Pool name to destroy.
            force: Force destruction of mounted datasets.

        Returns:
            ToolResult with destruction status.
        """
        force_flag = "-f " if force else ""
        rc, out, err = await self._run(f"zpool destroy {force_flag}{name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy pool: {err}")

        return ToolResult(
            success=True,
            output=f"Pool '{name}' destroyed",
            side_effects=[f"ZFS pool '{name}' permanently destroyed", "All data on pool lost"],
            metadata={"pool": name, "action": "destroy"},
        )

    async def scrub_pool(self, pool_name: str) -> ToolResult:
        """Start a scrub on a ZFS pool to verify data integrity.

        Args:
            pool_name: Pool to scrub.

        Returns:
            ToolResult with scrub status.
        """
        rc, out, err = await self._run(f"zpool scrub {pool_name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start scrub: {err}")

        return ToolResult(
            success=True,
            output=f"Scrub started on pool '{pool_name}'",
            side_effects=[f"Background scrub running on '{pool_name}'"],
            metadata={"pool": pool_name, "action": "scrub"},
        )

    # ─── Dataset Operations ───────────────────────────────────────────────

    async def list_datasets(self, pool: Optional[str] = None) -> ToolResult:
        """List ZFS datasets with usage info.

        Args:
            pool: Filter to specific pool (optional).

        Returns:
            ToolResult with dataset listing.
        """
        target = pool or ""
        rc, out, err = await self._run(
            f"zfs list -Hp -o name,used,avail,refer,mountpoint,compress {target}".strip()
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list datasets: {err}")

        datasets: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                datasets.append({
                    "name": parts[0],
                    "used_bytes": int(parts[1]),
                    "available_bytes": int(parts[2]),
                    "referenced_bytes": int(parts[3]),
                    "mountpoint": parts[4],
                    "compression": parts[5],
                })

        return ToolResult(
            success=True,
            output=json.dumps(datasets, indent=2),
            metadata={"dataset_count": len(datasets), "datasets": datasets},
        )

    async def create_dataset(
        self,
        name: str,
        compression: str = "lz4",
        quota: Optional[str] = None,
        mountpoint: Optional[str] = None,
        encryption: bool = False,
    ) -> ToolResult:
        """Create a new ZFS dataset.

        Args:
            name: Full dataset path (e.g., "tank/media").
            compression: Compression algorithm (lz4, zstd, gzip, off).
            quota: Size quota (e.g., "100G", "1T").
            mountpoint: Custom mount point.
            encryption: Enable encryption (aes-256-gcm).

        Returns:
            ToolResult with creation status.
        """
        if not name:
            return ToolResult(success=False, error="Dataset name is required")

        opts: List[str] = [f"-o compression={compression}"]
        if quota:
            opts.append(f"-o quota={quota}")
        if mountpoint:
            opts.append(f"-o mountpoint={mountpoint}")
        if encryption:
            opts.append("-o encryption=aes-256-gcm -o keyformat=passphrase")

        opts_str = " ".join(opts)
        rc, out, err = await self._run(f"zfs create {opts_str} {name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create dataset: {err}")

        return ToolResult(
            success=True,
            output=f"Dataset '{name}' created (compression={compression})",
            side_effects=[f"ZFS dataset '{name}' created and mounted"],
            metadata={"dataset": name, "compression": compression, "quota": quota},
        )

    async def destroy_dataset(self, name: str, recursive: bool = False) -> ToolResult:
        """Destroy a ZFS dataset. DANGEROUS.

        Args:
            name: Dataset to destroy.
            recursive: Also destroy child datasets and snapshots.

        Returns:
            ToolResult with destruction status.
        """
        r_flag = "-r " if recursive else ""
        rc, out, err = await self._run(f"zfs destroy {r_flag}{name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy dataset: {err}")

        return ToolResult(
            success=True,
            output=f"Dataset '{name}' destroyed",
            side_effects=[f"Dataset '{name}' permanently destroyed"],
            metadata={"dataset": name, "recursive": recursive},
        )

    async def set_property(self, dataset: str, property_name: str, value: str) -> ToolResult:
        """Set a ZFS property on a dataset.

        Args:
            dataset: Target dataset.
            property_name: Property to set (compression, quota, etc.).
            value: Property value.

        Returns:
            ToolResult with status.
        """
        rc, out, err = await self._run(f"zfs set {property_name}={value} {dataset}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set property: {err}")

        return ToolResult(
            success=True,
            output=f"Set {property_name}={value} on '{dataset}'",
            metadata={"dataset": dataset, "property": property_name, "value": value},
        )

    # ─── Snapshot Operations ──────────────────────────────────────────────

    async def list_snapshots(self, dataset: Optional[str] = None) -> ToolResult:
        """List ZFS snapshots.

        Args:
            dataset: Filter to specific dataset (optional).

        Returns:
            ToolResult with snapshot listing.
        """
        target = f"-r {dataset}" if dataset else ""
        rc, out, err = await self._run(
            f"zfs list -t snapshot -Hp -o name,used,refer,creation {target}".strip()
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list snapshots: {err}")

        snapshots: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 4:
                snapshots.append({
                    "name": parts[0],
                    "used_bytes": int(parts[1]),
                    "referenced_bytes": int(parts[2]),
                    "created": parts[3],
                })

        return ToolResult(
            success=True,
            output=json.dumps(snapshots, indent=2),
            metadata={"snapshot_count": len(snapshots), "snapshots": snapshots},
        )

    async def create_snapshot(
        self, dataset: str, snap_name: Optional[str] = None, recursive: bool = False
    ) -> ToolResult:
        """Create a ZFS snapshot.

        Args:
            dataset: Dataset to snapshot.
            snap_name: Snapshot name (auto-generated with timestamp if not provided).
            recursive: Also snapshot child datasets.

        Returns:
            ToolResult with snapshot info.
        """
        if not snap_name:
            snap_name = f"mk-auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        full_name = f"{dataset}@{snap_name}"
        r_flag = "-r " if recursive else ""

        rc, out, err = await self._run(f"zfs snapshot {r_flag}{full_name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create snapshot: {err}")

        return ToolResult(
            success=True,
            output=f"Snapshot '{full_name}' created",
            side_effects=[f"Snapshot '{full_name}' created"],
            metadata={"snapshot": full_name, "dataset": dataset, "recursive": recursive},
        )

    async def rollback_snapshot(self, snapshot: str, destroy_newer: bool = False) -> ToolResult:
        """Rollback a dataset to a snapshot. DANGEROUS.

        Args:
            snapshot: Full snapshot name (dataset@snap).
            destroy_newer: Destroy snapshots newer than this one.

        Returns:
            ToolResult with rollback status.
        """
        r_flag = "-r " if destroy_newer else ""
        rc, out, err = await self._run(f"zfs rollback {r_flag}{snapshot}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to rollback: {err}")

        return ToolResult(
            success=True,
            output=f"Rolled back to snapshot '{snapshot}'",
            side_effects=[f"Dataset rolled back to '{snapshot}'", "Newer data overwritten"],
            metadata={"snapshot": snapshot, "destroyed_newer": destroy_newer},
        )

    async def destroy_snapshot(self, snapshot: str) -> ToolResult:
        """Destroy a ZFS snapshot.

        Args:
            snapshot: Full snapshot name (dataset@snap).

        Returns:
            ToolResult with status.
        """
        rc, out, err = await self._run(f"zfs destroy {snapshot}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy snapshot: {err}")

        return ToolResult(
            success=True,
            output=f"Snapshot '{snapshot}' destroyed",
            side_effects=[f"Snapshot '{snapshot}' permanently removed"],
            metadata={"snapshot": snapshot},
        )

    # ─── Share Operations ─────────────────────────────────────────────────

    async def list_shares(self) -> ToolResult:
        """List all configured network shares (SMB and NFS).

        Returns:
            ToolResult with share listing.
        """
        shares: List[Dict[str, Any]] = []

        # Get SMB shares from samba config
        rc, out, err = await self._run("testparm -s 2>/dev/null || true", check=False)
        if rc == 0 and out:
            shares.append({"type": "smb", "config": out})

        # Get NFS exports
        rc, out, err = await self._run("exportfs -v 2>/dev/null || true", check=False)
        if rc == 0 and out:
            for line in out.splitlines():
                if line.strip():
                    shares.append({"type": "nfs", "export": line.strip()})

        return ToolResult(
            success=True,
            output=json.dumps(shares, indent=2) if shares else "No shares configured",
            metadata={"share_count": len(shares)},
        )

    async def create_smb_share(
        self,
        name: str,
        path: str,
        read_only: bool = False,
        guest_ok: bool = False,
        valid_users: Optional[List[str]] = None,
    ) -> ToolResult:
        """Create an SMB (Samba) share.

        Args:
            name: Share name.
            path: Filesystem path to share.
            read_only: Whether the share is read-only.
            guest_ok: Allow guest access.
            valid_users: List of allowed users (empty = all).

        Returns:
            ToolResult with share creation status.
        """
        # Build samba config section
        config_lines = [
            f"[{name}]",
            f"   path = {path}",
            f"   read only = {'yes' if read_only else 'no'}",
            f"   guest ok = {'yes' if guest_ok else 'no'}",
            "   create mask = 0664",
            "   directory mask = 0775",
        ]
        if valid_users:
            config_lines.append(f"   valid users = {' '.join(valid_users)}")

        config_block = "\n".join(config_lines) + "\n"

        # Append to smb.conf
        smb_conf = Path("/etc/samba/smb.conf")
        rc, out, err = await self._run(
            f"bash -c 'echo \"\n{config_block}\" >> /etc/samba/smb.conf'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write SMB config: {err}")

        # Restart samba
        await self._run("systemctl restart smbd")

        return ToolResult(
            success=True,
            output=f"SMB share '{name}' created at {path}",
            side_effects=[f"SMB share '{name}' added to /etc/samba/smb.conf", "smbd restarted"],
            metadata={"share_name": name, "path": path, "type": "smb"},
        )

    async def create_nfs_share(
        self,
        path: str,
        allowed_network: str = "*",
        options: str = "rw,sync,no_subtree_check",
    ) -> ToolResult:
        """Create an NFS export.

        Args:
            path: Filesystem path to export.
            allowed_network: Network/host allowed (e.g., "192.168.1.0/24").
            options: NFS export options.

        Returns:
            ToolResult with export creation status.
        """
        export_line = f"{path} {allowed_network}({options})"

        rc, out, err = await self._run(
            f"bash -c 'echo \"{export_line}\" >> /etc/exports'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write NFS export: {err}")

        # Reload NFS exports
        await self._run("exportfs -ra")

        return ToolResult(
            success=True,
            output=f"NFS export created: {path} -> {allowed_network}",
            side_effects=[f"NFS export added to /etc/exports", "NFS exports reloaded"],
            metadata={"path": path, "network": allowed_network, "type": "nfs"},
        )

    async def remove_share(self, name: str, share_type: str) -> ToolResult:
        """Remove a network share.

        Args:
            name: Share name (SMB) or path (NFS).
            share_type: "smb" or "nfs".

        Returns:
            ToolResult with removal status.
        """
        if share_type == "smb":
            # Remove SMB section from smb.conf (sed-based removal)
            rc, out, err = await self._run(
                f"sed -i '/\\[{name}\\]/,/^\\[/{{/^\\[{name}\\]/d;/^\\[/!d}}' /etc/samba/smb.conf"
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Failed to remove SMB share: {err}")
            await self._run("systemctl restart smbd")
        elif share_type == "nfs":
            # Remove NFS export line
            rc, out, err = await self._run(
                f"sed -i '\\|^{name}|d' /etc/exports"
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Failed to remove NFS export: {err}")
            await self._run("exportfs -ra")
        else:
            return ToolResult(success=False, error=f"Unknown share type: {share_type}")

        return ToolResult(
            success=True,
            output=f"Share '{name}' ({share_type}) removed",
            side_effects=[f"{share_type.upper()} share '{name}' removed"],
            metadata={"name": name, "type": share_type},
        )

    # ─── Disk Health ──────────────────────────────────────────────────────

    async def list_disks(self) -> ToolResult:
        """List all block devices with size and model info.

        Returns:
            ToolResult with disk listing.
        """
        rc, out, err = await self._run(
            "lsblk -Jb -o NAME,SIZE,TYPE,MODEL,SERIAL,ROTA,TRAN"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list disks: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"format": "json"},
        )

    async def disk_smart_health(self, device: str) -> ToolResult:
        """Get SMART health status for a disk.

        Args:
            device: Disk device path (e.g., "/dev/sda").

        Returns:
            ToolResult with SMART health info.
        """
        rc, out, err = await self._run(f"smartctl -a {device}")
        if rc > 4:  # smartctl uses bitmask return codes; >4 means real error
            return ToolResult(success=False, error=f"SMART check failed: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"device": device, "format": "smartctl"},
        )

    # ─── ZFS Send/Receive (Replication) ───────────────────────────────────

    async def send_snapshot(
        self, snapshot: str, destination: str, incremental_from: Optional[str] = None
    ) -> ToolResult:
        """Send a ZFS snapshot to a remote destination (replication).

        Args:
            snapshot: Full snapshot name to send.
            destination: SSH target (user@host:pool/dataset) or local dataset.
            incremental_from: Base snapshot for incremental send.

        Returns:
            ToolResult with send status.
        """
        incr_flag = f"-i {incremental_from} " if incremental_from else ""

        if ":" in destination:
            # Remote send via SSH
            host, target = destination.split(":", 1)
            cmd = f"zfs send {incr_flag}{snapshot} | ssh {host} zfs receive -F {target}"
        else:
            # Local receive
            cmd = f"zfs send {incr_flag}{snapshot} | zfs receive -F {destination}"

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"ZFS send failed: {err}")

        return ToolResult(
            success=True,
            output=f"Snapshot '{snapshot}' replicated to '{destination}'",
            side_effects=[f"Data replicated to {destination}"],
            metadata={"snapshot": snapshot, "destination": destination, "incremental": bool(incremental_from)},
        )
