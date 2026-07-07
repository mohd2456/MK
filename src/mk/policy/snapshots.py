"""Snapshot manager — pre-execution state capture for rollback.

Before any risky operation, MK captures the current state so it
can be restored if things go wrong. Snapshot types:
- ZFS snapshots (atomic, instant, free until space needed)
- Config file backups (copy before edit)
- Container commits (save container state)
- Service state (what was running, how it was configured)

The snapshot manager creates these automatically when the policy
engine requires a snapshot, and provides them to the rollback
handler when things need to be undone.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SnapshotType(str, Enum):
    """Types of snapshots MK can create."""

    ZFS = "zfs"                 # ZFS snapshot (instant, atomic)
    FILE = "file"               # File/config backup (copy)
    CONTAINER = "container"     # Docker container commit
    SERVICE_STATE = "service"   # Service configuration state
    COMPOSITE = "composite"     # Multiple snapshots grouped together


@dataclass
class Snapshot:
    """A single state snapshot.

    Represents a captured state that can be rolled back to.
    """

    id: str
    snapshot_type: SnapshotType
    target: str  # What was snapshotted (path, dataset, container name)
    description: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Rollback info
    rollback_command: Optional[str] = None
    rollback_steps: List[str] = field(default_factory=list)

    # State
    used_for_rollback: bool = False
    expired: bool = False

    @property
    def age_seconds(self) -> float:
        """How old this snapshot is."""
        return time.time() - self.created_at

    @property
    def age_human(self) -> str:
        """Human-readable age."""
        age = self.age_seconds
        if age < 60:
            return f"{age:.0f}s"
        elif age < 3600:
            return f"{age / 60:.0f}m"
        elif age < 86400:
            return f"{age / 3600:.1f}h"
        return f"{age / 86400:.1f}d"

    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"[{self.snapshot_type.value}] {self.target} "
            f"({self.age_human} ago) — {self.description}"
        )


class SnapshotManager:
    """Manages pre-execution state snapshots.

    Creates snapshots before risky operations and tracks them
    for potential rollback. Old snapshots are cleaned up after
    a configurable retention period.

    In production:
    - ZFS: runs `zfs snapshot pool/dataset@mk-{timestamp}`
    - Files: copies to ~/.mk/snapshots/{id}/
    - Containers: runs `docker commit {container} mk-snap-{id}`
    - Services: captures systemctl show output

    For now, simulates these operations with local file tracking.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_snapshots: int = 100,
        retention_hours: float = 72.0,
    ) -> None:
        """Initialize the snapshot manager.

        Args:
            storage_path: Where to store snapshot data.
            max_snapshots: Maximum snapshots to keep.
            retention_hours: How long to keep snapshots.
        """
        self._storage_path = Path(
            storage_path or Path.home() / ".mk" / "snapshots"
        )
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._snapshots: Dict[str, Snapshot] = {}
        self._max_snapshots = max_snapshots
        self._retention_hours = retention_hours

    @property
    def count(self) -> int:
        """Number of active snapshots."""
        return len(self._snapshots)

    @property
    def active_snapshots(self) -> List[Snapshot]:
        """All non-expired snapshots, newest first."""
        active = [s for s in self._snapshots.values() if not s.expired]
        return sorted(active, key=lambda s: s.created_at, reverse=True)

    async def create_snapshot(
        self,
        target: str,
        snapshot_type: SnapshotType,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Snapshot:
        """Create a new snapshot of the target.

        Args:
            target: What to snapshot (path, dataset, container).
            snapshot_type: Type of snapshot to create.
            description: Why this snapshot was created.
            metadata: Additional context.

        Returns:
            The created Snapshot.
        """
        snapshot_id = f"snap-{uuid.uuid4().hex[:8]}"

        # Determine rollback command based on type
        rollback_command = self._build_rollback_command(
            snapshot_type, target, snapshot_id
        )

        snapshot = Snapshot(
            id=snapshot_id,
            snapshot_type=snapshot_type,
            target=target,
            description=description,
            metadata=metadata or {},
            rollback_command=rollback_command,
        )

        # Execute the actual snapshot creation
        await self._execute_snapshot(snapshot)

        self._snapshots[snapshot_id] = snapshot
        self._cleanup_old()

        logger.info(f"Snapshot created: {snapshot.summary()}")
        return snapshot

    async def create_composite(
        self,
        targets: List[Dict[str, Any]],
        description: str = "",
    ) -> Snapshot:
        """Create a composite snapshot (multiple targets at once).

        Useful for operations that affect multiple things.

        Args:
            targets: List of {target, type} dicts.
            description: Why this composite snapshot exists.

        Returns:
            Composite Snapshot containing sub-snapshots.
        """
        sub_snapshots: List[str] = []
        for t in targets:
            sub = await self.create_snapshot(
                target=t["target"],
                snapshot_type=SnapshotType(t.get("type", "file")),
                description=f"Part of: {description}",
            )
            sub_snapshots.append(sub.id)

        # Create the composite
        composite_id = f"comp-{uuid.uuid4().hex[:8]}"
        composite = Snapshot(
            id=composite_id,
            snapshot_type=SnapshotType.COMPOSITE,
            target="composite",
            description=description,
            metadata={"sub_snapshots": sub_snapshots},
            rollback_steps=[
                f"rollback {sid}" for sid in reversed(sub_snapshots)
            ],
        )
        self._snapshots[composite_id] = composite
        return composite

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get a snapshot by ID."""
        return self._snapshots.get(snapshot_id)

    def get_latest_for_target(self, target: str) -> Optional[Snapshot]:
        """Get the most recent snapshot for a target.

        Args:
            target: The target to find snapshots for.

        Returns:
            Most recent Snapshot for this target, or None.
        """
        matching = [
            s for s in self._snapshots.values()
            if s.target == target and not s.expired
        ]
        if not matching:
            return None
        return max(matching, key=lambda s: s.created_at)

    def expire_snapshot(self, snapshot_id: str) -> bool:
        """Mark a snapshot as expired (can be cleaned up).

        Args:
            snapshot_id: Snapshot to expire.

        Returns:
            True if found and expired.
        """
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot:
            snapshot.expired = True
            return True
        return False

    async def _execute_snapshot(self, snapshot: Snapshot) -> None:
        """Execute the actual snapshot creation.

        In production, this runs the appropriate command:
        - ZFS: `zfs snapshot {target}@{id}`
        - File: `cp -a {target} {storage}/{id}/`
        - Container: `docker commit {target} mk-snap-{id}`
        """
        # For now, record the snapshot metadata to disk
        snap_dir = self._storage_path / snapshot.id
        snap_dir.mkdir(exist_ok=True)

        info = {
            "id": snapshot.id,
            "type": snapshot.snapshot_type.value,
            "target": snapshot.target,
            "description": snapshot.description,
            "created_at": snapshot.created_at,
            "rollback_command": snapshot.rollback_command,
            "metadata": snapshot.metadata,
        }

        with open(snap_dir / "info.json", "w") as f:
            json.dump(info, f, indent=2)

        # If it's a file snapshot, actually copy the file (if it exists)
        if snapshot.snapshot_type == SnapshotType.FILE:
            source = Path(snapshot.target)
            if source.exists():
                dest = snap_dir / source.name
                if source.is_file():
                    shutil.copy2(str(source), str(dest))
                # Don't copy directories in this implementation

    def _build_rollback_command(
        self, snapshot_type: SnapshotType, target: str, snapshot_id: str
    ) -> str:
        """Build the rollback command for a snapshot type."""
        commands = {
            SnapshotType.ZFS: f"zfs rollback {target}@{snapshot_id}",
            SnapshotType.FILE: f"cp -a ~/.mk/snapshots/{snapshot_id}/{Path(target).name} {target}",
            SnapshotType.CONTAINER: f"docker stop {target} && docker rm {target} && docker run --name {target} mk-snap-{snapshot_id}",
            SnapshotType.SERVICE_STATE: f"systemctl restart {target}",
        }
        return commands.get(snapshot_type, f"# Manual rollback needed for {target}")

    def _cleanup_old(self) -> None:
        """Remove expired and old snapshots."""
        now = time.time()
        cutoff = now - (self._retention_hours * 3600)

        # Mark old ones as expired
        for snapshot in self._snapshots.values():
            if snapshot.created_at < cutoff and not snapshot.used_for_rollback:
                snapshot.expired = True

        # Remove expired if over max
        if len(self._snapshots) > self._max_snapshots:
            expired = [
                sid for sid, s in self._snapshots.items()
                if s.expired
            ]
            for sid in expired[:len(self._snapshots) - self._max_snapshots]:
                # Clean up disk
                snap_dir = self._storage_path / sid
                if snap_dir.exists():
                    shutil.rmtree(snap_dir, ignore_errors=True)
                del self._snapshots[sid]

    def list_snapshots(self, target: Optional[str] = None) -> List[Snapshot]:
        """List snapshots, optionally filtered by target.

        Args:
            target: Filter by target (None for all).

        Returns:
            List of snapshots, newest first.
        """
        snapshots = list(self._snapshots.values())
        if target:
            snapshots = [s for s in snapshots if s.target == target]
        return sorted(snapshots, key=lambda s: s.created_at, reverse=True)

    def get_status(self) -> Dict[str, Any]:
        """Get snapshot manager status."""
        active = [s for s in self._snapshots.values() if not s.expired]
        return {
            "total_snapshots": len(self._snapshots),
            "active_snapshots": len(active),
            "by_type": {
                t.value: sum(1 for s in active if s.snapshot_type == t)
                for t in SnapshotType
                if sum(1 for s in active if s.snapshot_type == t) > 0
            },
            "storage_path": str(self._storage_path),
        }
