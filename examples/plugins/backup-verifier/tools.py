"""Backup Verifier Plugin — tools implementation.

Verifies backup integrity by:
1. Listing available snapshots
2. Checking backup freshness (age)
3. Restoring random sample files and verifying checksums

This plugin demonstrates the MK plugin pattern:
- Each function matches a tool name declared in plugin.yaml
- Functions are async and return ToolResult (or a string/dict)
- The plugin.yaml declares permissions needed (filesystem:read, shell:exec)
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from mk.plugins.decorators import plugin_tool
from mk.tools.base import ToolResult


@plugin_tool(description="Verify the latest backup by restoring and checksumming random files")
async def verify_latest(pool: str = "tank/backups", sample_count: int = 5) -> ToolResult:
    """Verify backup integrity by sampling files.

    Steps:
    1. Find the latest snapshot for the pool
    2. Pick N random files from the snapshot
    3. Read each file and compute checksum
    4. Compare against stored checksums

    Args:
        pool: The backup pool/target to verify.
        sample_count: Number of random files to check.

    Returns:
        ToolResult with verification summary.
    """
    # In production: run `zfs list -t snapshot -o name,creation -s creation {pool}`
    # For now, simulate the verification flow

    start = time.time()

    # Simulate finding snapshots
    snapshot_name = f"{pool}@auto-{datetime.utcnow().strftime('%Y%m%d')}"

    # Simulate file sampling and verification
    verified_files: List[Dict[str, str]] = []
    failed_files: List[Dict[str, str]] = []

    for i in range(sample_count):
        # In production: list files in snapshot, pick random, checksum
        file_path = f"/data/file_{i + 1}.dat"
        status = "pass"  # Would be actual checksum comparison
        verified_files.append({"path": file_path, "status": status})

    elapsed = time.time() - start
    all_passed = len(failed_files) == 0

    summary_lines = [
        f"Backup verification: {'PASS' if all_passed else 'FAIL'}",
        f"Snapshot: {snapshot_name}",
        f"Files checked: {sample_count}",
        f"Passed: {len(verified_files)}",
        f"Failed: {len(failed_files)}",
        f"Duration: {elapsed:.1f}s",
    ]

    if failed_files:
        summary_lines.append("\nFailed files:")
        for f in failed_files:
            summary_lines.append(f"  - {f['path']}: {f.get('reason', 'checksum mismatch')}")

    return ToolResult(
        success=all_passed,
        output="\n".join(summary_lines),
        metadata={
            "snapshot": snapshot_name,
            "files_checked": sample_count,
            "files_passed": len(verified_files),
            "files_failed": len(failed_files),
            "elapsed_seconds": elapsed,
        },
    )


@plugin_tool(description="Check if backups are stale (older than threshold)")
async def check_age(max_age_hours: int = 24) -> ToolResult:
    """Check backup freshness.

    Compares the most recent backup timestamp against the threshold.
    Raises an alert if backups are stale.

    Args:
        max_age_hours: Maximum acceptable backup age in hours.

    Returns:
        ToolResult indicating whether backups are fresh.
    """
    # In production: parse `zfs list -t snapshot -o creation -s creation`
    # and compare the latest against now

    # Simulate: last backup was 6 hours ago
    simulated_last_backup = datetime.utcnow() - timedelta(hours=6)
    age_hours = (datetime.utcnow() - simulated_last_backup).total_seconds() / 3600

    is_fresh = age_hours <= max_age_hours

    status = "FRESH" if is_fresh else "STALE"
    output = (
        f"Backup status: {status}\n"
        f"Last backup: {simulated_last_backup.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Age: {age_hours:.1f} hours (threshold: {max_age_hours}h)"
    )

    if not is_fresh:
        output += f"\n⚠️ Backups are {age_hours:.1f}h old — exceeds {max_age_hours}h threshold!"

    return ToolResult(
        success=is_fresh,
        output=output,
        metadata={
            "last_backup": simulated_last_backup.isoformat(),
            "age_hours": round(age_hours, 1),
            "threshold_hours": max_age_hours,
            "is_fresh": is_fresh,
        },
    )


@plugin_tool(description="List all available backup snapshots with timestamps")
async def list_backups(pool: str = "", limit: int = 10) -> ToolResult:
    """List available backup snapshots.

    Args:
        pool: Pool to filter by (empty for all).
        limit: Maximum number of snapshots to list.

    Returns:
        ToolResult with snapshot listing.
    """
    # In production: `zfs list -t snapshot -o name,creation,used -s creation`

    # Simulate snapshot listing
    now = datetime.utcnow()
    snapshots = []
    for i in range(min(limit, 7)):
        ts = now - timedelta(days=i)
        snapshots.append({
            "name": f"tank/backups@auto-{ts.strftime('%Y%m%d')}",
            "created": ts.strftime("%Y-%m-%d %H:%M"),
            "size": f"{random.randint(1, 50)}G",
        })

    lines = [f"{'Snapshot':<45} {'Created':<20} {'Size':<8}"]
    lines.append("-" * 73)
    for snap in snapshots:
        lines.append(f"{snap['name']:<45} {snap['created']:<20} {snap['size']:<8}")

    lines.append(f"\nTotal: {len(snapshots)} snapshots")

    return ToolResult(
        success=True,
        output="\n".join(lines),
        metadata={
            "count": len(snapshots),
            "pool": pool or "all",
            "snapshots": snapshots,
        },
    )
