"""Storage Manager - ZFS pool, dataset, snapshot, and share management."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from ._shell import safe_quote, validate_name

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages ZFS storage pools, datasets, snapshots, and network shares."""

    def __init__(self, sudo: bool = True) -> None:
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
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
            logger.debug(f"Command failed ({rc}): {full_cmd}\n{err}")

        return rc, out, err

    async def _run_with_stdin(self, cmd: str, input_data: str) -> Tuple[int, str, str]:
        """Execute a shell command with data passed via stdin."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Storage exec (stdin): {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=input_data.encode())
        rc = proc.returncode or 0
        return rc, stdout.decode().strip(), stderr.decode().strip()

    # Pool Operations

    async def list_pools(self) -> ToolResult:
        """List all ZFS pools with their status and usage."""
        rc, out, err = await self._run("zpool list -Hp -o name,size,alloc,free,frag,health")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list pools: {err}")

        pools: List[Dict[str, Any]] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                name, size, alloc, free, frag, health = parts[:6]
                pools.append(
                    {
                        "name": name,
                        "size_bytes": int(size),
                        "used_bytes": int(alloc),
                        "free_bytes": int(free),
                        "fragmentation": int(frag.rstrip("%")) if frag != "-" else 0,
                        "status": health.lower(),
                    }
                )

        return ToolResult(
            success=True,
            output=json.dumps(pools, indent=2),
            metadata={"pool_count": len(pools), "pools": pools},
        )

    async def pool_status(self, pool_name: str) -> ToolResult:
        """Get detailed status of a specific pool."""
        validate_name(pool_name, "pool_name")
        rc, out, err = await self._run(f"zpool status {safe_quote(pool_name)}")
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
        """Create a new ZFS pool."""
        if not name:
            return ToolResult(success=False, error="Pool name is required")
        if not disks:
            return ToolResult(success=False, error="At least one disk is required")

        validate_name(name, "pool name")

        valid_types = ["mirror", "raidz1", "raidz2", "raidz3", "stripe"]
        if vdev_type not in valid_types:
            return ToolResult(
                success=False,
                error=f"Invalid vdev type '{vdev_type}'. Use: {', '.join(valid_types)}",
            )

        # Validate disk paths
        for disk in disks:
            validate_name(disk, "disk path")

        force_flag = "-f " if force else ""
        vdev_arg = "" if vdev_type == "stripe" else f"{vdev_type} "
        disk_args = " ".join(safe_quote(d) for d in disks)
        cmd = f"zpool create {force_flag}{safe_quote(name)} {vdev_arg}{disk_args}"

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create pool: {err}")

        return ToolResult(
            success=True,
            output=f"Pool '{name}' created with {vdev_type} topology using {len(disks)} disks",
            side_effects=[f"ZFS pool '{name}' created", f"Disks allocated: {', '.join(disks)}"],
            metadata={"pool": name, "vdev_type": vdev_type, "disks": disks},
        )

    async def destroy_pool(self, name: str, force: bool = False) -> ToolResult:
        """Destroy a ZFS pool."""
        validate_name(name, "pool name")
        force_flag = "-f " if force else ""
        rc, out, err = await self._run(f"zpool destroy {force_flag}{safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy pool: {err}")

        return ToolResult(
            success=True,
            output=f"Pool '{name}' destroyed",
            side_effects=[f"ZFS pool '{name}' permanently destroyed", "All data on pool lost"],
            metadata={"pool": name, "action": "destroy"},
        )

    async def scrub_pool(self, pool_name: str) -> ToolResult:
        """Start a scrub on a ZFS pool to verify data integrity."""
        validate_name(pool_name, "pool_name")
        rc, out, err = await self._run(f"zpool scrub {safe_quote(pool_name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to start scrub: {err}")

        return ToolResult(
            success=True,
            output=f"Scrub started on pool '{pool_name}'",
            side_effects=[f"Background scrub running on '{pool_name}'"],
            metadata={"pool": pool_name, "action": "scrub"},
        )

    # Dataset Operations

    async def list_datasets(self, pool: Optional[str] = None) -> ToolResult:
        """List ZFS datasets with usage info."""
        if pool:
            validate_name(pool, "pool")
        target = safe_quote(pool) if pool else ""
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
                datasets.append(
                    {
                        "name": parts[0],
                        "used_bytes": int(parts[1]),
                        "available_bytes": int(parts[2]),
                        "referenced_bytes": int(parts[3]),
                        "mountpoint": parts[4],
                        "compression": parts[5],
                    }
                )

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
        """Create a new ZFS dataset."""
        if not name:
            return ToolResult(success=False, error="Dataset name is required")
        validate_name(name, "dataset name")

        opts: List[str] = [f"-o compression={safe_quote(compression)}"]
        if quota:
            validate_name(quota, "quota")
            opts.append(f"-o quota={safe_quote(quota)}")
        if mountpoint:
            opts.append(f"-o mountpoint={safe_quote(mountpoint)}")
        if encryption:
            opts.append("-o encryption=aes-256-gcm -o keyformat=passphrase")

        opts_str = " ".join(opts)
        rc, out, err = await self._run(f"zfs create {opts_str} {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create dataset: {err}")

        return ToolResult(
            success=True,
            output=f"Dataset '{name}' created (compression={compression})",
            side_effects=[f"ZFS dataset '{name}' created and mounted"],
            metadata={"dataset": name, "compression": compression, "quota": quota},
        )

    async def destroy_dataset(self, name: str, recursive: bool = False) -> ToolResult:
        """Destroy a ZFS dataset."""
        validate_name(name, "dataset name")
        r_flag = "-r " if recursive else ""
        rc, out, err = await self._run(f"zfs destroy {r_flag}{safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy dataset: {err}")

        return ToolResult(
            success=True,
            output=f"Dataset '{name}' destroyed",
            side_effects=[f"Dataset '{name}' permanently destroyed"],
            metadata={"dataset": name, "recursive": recursive},
        )

    async def set_property(self, dataset: str, property_name: str, value: str) -> ToolResult:
        """Set a ZFS property on a dataset."""
        validate_name(dataset, "dataset")
        validate_name(property_name, "property_name")
        rc, out, err = await self._run(
            f"zfs set {safe_quote(property_name)}={safe_quote(value)} {safe_quote(dataset)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set property: {err}")

        return ToolResult(
            success=True,
            output=f"Set {property_name}={value} on '{dataset}'",
            metadata={"dataset": dataset, "property": property_name, "value": value},
        )

    # Snapshot Operations

    async def list_snapshots(self, dataset: Optional[str] = None) -> ToolResult:
        """List ZFS snapshots."""
        if dataset:
            validate_name(dataset, "dataset")
        target = f"-r {safe_quote(dataset)}" if dataset else ""
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
                snapshots.append(
                    {
                        "name": parts[0],
                        "used_bytes": int(parts[1]),
                        "referenced_bytes": int(parts[2]),
                        "created": parts[3],
                    }
                )

        return ToolResult(
            success=True,
            output=json.dumps(snapshots, indent=2),
            metadata={"snapshot_count": len(snapshots), "snapshots": snapshots},
        )

    async def create_snapshot(
        self, dataset: str, snap_name: Optional[str] = None, recursive: bool = False
    ) -> ToolResult:
        """Create a ZFS snapshot."""
        validate_name(dataset, "dataset")
        if not snap_name:
            snap_name = f"mk-auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        else:
            validate_name(snap_name, "snapshot name")

        full_name = f"{dataset}@{snap_name}"
        r_flag = "-r " if recursive else ""

        rc, out, err = await self._run(f"zfs snapshot {r_flag}{safe_quote(full_name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create snapshot: {err}")

        return ToolResult(
            success=True,
            output=f"Snapshot '{full_name}' created",
            side_effects=[f"Snapshot '{full_name}' created"],
            metadata={"snapshot": full_name, "dataset": dataset, "recursive": recursive},
        )

    async def rollback_snapshot(self, snapshot: str, destroy_newer: bool = False) -> ToolResult:
        """Rollback a dataset to a snapshot."""
        validate_name(snapshot, "snapshot")
        r_flag = "-r " if destroy_newer else ""
        rc, out, err = await self._run(f"zfs rollback {r_flag}{safe_quote(snapshot)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to rollback: {err}")

        return ToolResult(
            success=True,
            output=f"Rolled back to snapshot '{snapshot}'",
            side_effects=[f"Dataset rolled back to '{snapshot}'", "Newer data overwritten"],
            metadata={"snapshot": snapshot, "destroyed_newer": destroy_newer},
        )

    async def destroy_snapshot(self, snapshot: str) -> ToolResult:
        """Destroy a ZFS snapshot."""
        validate_name(snapshot, "snapshot")
        rc, out, err = await self._run(f"zfs destroy {safe_quote(snapshot)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to destroy snapshot: {err}")

        return ToolResult(
            success=True,
            output=f"Snapshot '{snapshot}' destroyed",
            side_effects=[f"Snapshot '{snapshot}' permanently removed"],
            metadata={"snapshot": snapshot},
        )

    # Share Operations

    async def list_shares(self) -> ToolResult:
        """List all configured network shares (SMB and NFS)."""
        shares: List[Dict[str, Any]] = []

        rc, out, err = await self._run("testparm -s 2>/dev/null || true", check=False)
        if rc == 0 and out:
            shares.append({"type": "smb", "config": out})

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
        """Create an SMB (Samba) share."""
        validate_name(name, "share name")

        config_lines = [
            f"[{name}]",
            f"   path = {path}",
            f"   read only = {'yes' if read_only else 'no'}",
            f"   guest ok = {'yes' if guest_ok else 'no'}",
            "   create mask = 0664",
            "   directory mask = 0775",
        ]
        if valid_users:
            for u in valid_users:
                validate_name(u, "valid_user")
            config_lines.append(f"   valid users = {' '.join(valid_users)}")

        config_block = "\n".join(config_lines) + "\n"

        # Write config via stdin to avoid shell interpolation issues
        rc, _, err = await self._run_with_stdin(
            "tee -a /etc/samba/smb.conf > /dev/null", "\n" + config_block
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write SMB config: {err}")

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
        """Create an NFS export."""
        export_line = f"{path} {allowed_network}({options})"

        # Write export via stdin to avoid shell interpolation issues
        rc, _, err = await self._run_with_stdin(
            "tee -a /etc/exports > /dev/null", export_line + "\n"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write NFS export: {err}")

        await self._run("exportfs -ra")

        return ToolResult(
            success=True,
            output=f"NFS export created: {path} -> {allowed_network}",
            side_effects=["NFS export added to /etc/exports", "NFS exports reloaded"],
            metadata={"path": path, "network": allowed_network, "type": "nfs"},
        )

    async def remove_share(self, name: str, share_type: str) -> ToolResult:
        """Remove a network share."""
        validate_name(name, "share name")

        # Escape regex metacharacters in name for safe sed usage
        escaped_name = name.replace(".", "\\.").replace("@", "\\@")

        if share_type == "smb":
            rc, out, err = await self._run(
                f"sed -i '/\\[{escaped_name}\\]/,/^\\[/{{/^\\[{escaped_name}\\]/d;/^\\[/!d}}' /etc/samba/smb.conf"
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Failed to remove SMB share: {err}")
            await self._run("systemctl restart smbd")
        elif share_type == "nfs":
            rc, out, err = await self._run(f"sed -i '\\|^{escaped_name}|d' /etc/exports")
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

    # Disk Health

    async def list_disks(self) -> ToolResult:
        """List all block devices with size and model info."""
        rc, out, err = await self._run("lsblk -Jb -o NAME,SIZE,TYPE,MODEL,SERIAL,ROTA,TRAN")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list disks: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"format": "json"},
        )

    async def disk_smart_health(self, device: str) -> ToolResult:
        """Get SMART health status for a disk."""
        validate_name(device, "device path")
        rc, out, err = await self._run(f"smartctl -a {safe_quote(device)}")
        if rc > 4:
            return ToolResult(success=False, error=f"SMART check failed: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"device": device, "format": "smartctl"},
        )

    # ZFS Send/Receive (Replication)

    async def send_snapshot(
        self, snapshot: str, destination: str, incremental_from: Optional[str] = None
    ) -> ToolResult:
        """Send a ZFS snapshot to a remote destination (replication)."""
        validate_name(snapshot, "snapshot")
        incr_flag = f"-i {safe_quote(incremental_from)} " if incremental_from else ""

        if ":" in destination:
            host, target = destination.split(":", 1)
            validate_name(host, "host")
            validate_name(target, "target dataset")
            cmd = (
                f"zfs send {incr_flag}{safe_quote(snapshot)} | "
                f"ssh {safe_quote(host)} zfs receive -F {safe_quote(target)}"
            )
        else:
            validate_name(destination, "destination dataset")
            cmd = f"zfs send {incr_flag}{safe_quote(snapshot)} | zfs receive -F {safe_quote(destination)}"

        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"ZFS send failed: {err}")

        return ToolResult(
            success=True,
            output=f"Snapshot '{snapshot}' replicated to '{destination}'",
            side_effects=[f"Data replicated to {destination}"],
            metadata={
                "snapshot": snapshot,
                "destination": destination,
                "incremental": bool(incremental_from),
            },
        )
