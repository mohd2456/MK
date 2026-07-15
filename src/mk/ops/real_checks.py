"""Real system checks using actual commands (not simulated).

These replace the simulated checks from ``checks.py`` with real command
execution. Each check is lightweight (subprocess with short timeout), runs
in the scheduler's async loop, and returns a :class:`CheckResult`.

Design: defensive — if a command isn't available or times out, the check
returns OK or UNKNOWN rather than crashing the scheduler.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Tuple

from mk.ops.checks import CheckResult, CheckSeverity


async def _run(cmd: str, timeout: float = 10.0) -> Tuple[int, str]:
    """Run a command, returning (returncode, stdout). Never raises."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode().strip()
    except (asyncio.TimeoutError, OSError):
        return 1, ""


# ─── Container health (real docker ps) ────────────────────────────────────────


async def real_container_health() -> CheckResult:
    """Check Docker container status using real `docker ps`."""
    rc, out = await _run("docker ps -a --format '{{.Names}}\\t{{.State}}' 2>/dev/null")
    if rc != 0 or not out.strip():
        # Docker not available or no containers
        return CheckResult(
            name="container_health",
            severity=CheckSeverity.OK,
            message="No containers (Docker unavailable or empty)",
        )

    containers = []
    for line in out.splitlines():
        parts = line.split("\\t")
        if len(parts) >= 2:
            containers.append({"name": parts[0], "state": parts[1]})

    unhealthy = [c for c in containers if c["state"] not in ("running", "created")]
    if unhealthy:
        names = [c["name"] for c in unhealthy]
        return CheckResult(
            name="container_health",
            severity=CheckSeverity.CRITICAL,
            message=f"Containers down: {', '.join(names[:5])}",
            data={"unhealthy": unhealthy, "total": len(containers)},
            recommendations=[
                f"Check logs: docker logs {names[0]}",
                f"Restart: docker restart {names[0]}",
            ],
        )

    return CheckResult(
        name="container_health",
        severity=CheckSeverity.OK,
        message=f"All {len(containers)} containers running",
        data={"total": len(containers)},
    )


# ─── Disk space (real df / zpool) ─────────────────────────────────────────────


async def real_disk_health() -> CheckResult:
    """Check real disk usage via df and zpool (if available)."""
    issues = []

    # Root filesystem
    try:
        st = os.statvfs("/")
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        pct = ((total - free) / total * 100) if total > 0 else 0
        free_gb = free / (1024**3)
        if pct > 95:
            issues.append(f"Root filesystem {pct:.0f}% full ({free_gb:.1f}GB free)")
        elif pct > 85:
            issues.append(f"Root filesystem {pct:.0f}% used ({free_gb:.1f}GB free)")
    except OSError:
        pass

    # ZFS pools (if available)
    rc, out = await _run("zpool list -H -o name,cap,health 2>/dev/null")
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                pool, cap_str, health = parts[0], parts[1], parts[2]
                cap = int(cap_str.rstrip("%")) if cap_str.rstrip("%").isdigit() else 0
                if health.upper() != "ONLINE":
                    issues.append(f"ZFS pool '{pool}' is {health}")
                elif cap > 90:
                    issues.append(f"ZFS pool '{pool}' is {cap}% full")

    if any("DEGRADED" in i or "FAULTED" in i for i in issues):
        return CheckResult(
            name="disk_health",
            severity=CheckSeverity.CRITICAL,
            message=issues[0],
            data={"issues": issues},
            recommendations=["Check: zpool status", "Consider replacement"],
        )
    if issues:
        return CheckResult(
            name="disk_health",
            severity=CheckSeverity.WARNING,
            message="; ".join(issues[:2]),
            data={"issues": issues},
            recommendations=["Free space or expand storage"],
        )

    return CheckResult(
        name="disk_health",
        severity=CheckSeverity.OK,
        message="All filesystems healthy",
    )


# ─── Backup freshness (real ZFS snapshots) ────────────────────────────────────


async def real_backup_freshness() -> CheckResult:
    """Check age of the most recent ZFS backup snapshot."""
    rc, out = await _run(
        "zfs list -t snapshot -H -o name,creation -S creation 2>/dev/null | head -1"
    )
    if rc != 0 or not out.strip():
        # No ZFS → check if any backup job configs exist
        rc2, out2 = await _run("find /etc/mk/backups -name '*.json' 2>/dev/null | wc -l")
        if rc2 == 0 and out2.strip() != "0":
            return CheckResult(
                name="backup_freshness",
                severity=CheckSeverity.WARNING,
                message="Backup jobs configured but no snapshots found",
                recommendations=["Run a backup manually to verify the pipeline"],
            )
        return CheckResult(
            name="backup_freshness",
            severity=CheckSeverity.OK,
            message="No backup system configured (ZFS not available)",
        )

    # Parse creation time (ZFS reports in locale-dependent format)
    # Try to get the most recent snapshot age in seconds via zfs get
    parts = out.split("\t")
    snap_name = parts[0] if parts else "unknown"
    # Use `zfs get creation` which gives epoch-parseable format
    rc3, epoch_out = await _run(f"zfs get -Hp -o value creation {snap_name.split()[0]} 2>/dev/null")
    if rc3 == 0 and epoch_out.strip().isdigit():
        age_seconds = time.time() - int(epoch_out.strip())
        age_hours = age_seconds / 3600
        if age_hours > 48:
            return CheckResult(
                name="backup_freshness",
                severity=CheckSeverity.CRITICAL,
                message=f"Latest backup is {age_hours:.0f}h old (>48h stale)",
                recommendations=["Run backup NOW", "Check backup timer/cron"],
            )
        elif age_hours > 26:
            return CheckResult(
                name="backup_freshness",
                severity=CheckSeverity.WARNING,
                message=f"Latest backup is {age_hours:.0f}h old (expected daily)",
                recommendations=["Verify nightly backup ran"],
            )
        return CheckResult(
            name="backup_freshness",
            severity=CheckSeverity.OK,
            message=f"Latest backup: {snap_name.split('@')[1] if '@' in snap_name else snap_name} ({age_hours:.0f}h ago)",
        )

    return CheckResult(
        name="backup_freshness",
        severity=CheckSeverity.OK,
        message="Backup system present",
    )


# ─── Service health (real HTTP pings) ─────────────────────────────────────────


async def real_service_health() -> CheckResult:
    """Ping configured services via HTTP and report availability.

    Checks common homelab ports that are expected to be running.
    """
    services = [
        ("plex", "http://localhost:32400/identity"),
        ("sonarr", "http://localhost:8989/ping"),
        ("radarr", "http://localhost:7878/ping"),
    ]

    down = []
    up = 0
    for name, url in services:
        rc, _ = await _run(f"curl -s -o /dev/null -w '%{{http_code}}' -m 5 {url} 2>/dev/null")
        if rc != 0:
            # curl itself failed (service not running / connection refused)
            down.append(name)
        else:
            up += 1

    total = len(services)
    if down and len(down) == total:
        # All down — probably no services configured; don't alarm
        return CheckResult(
            name="service_health",
            severity=CheckSeverity.OK,
            message="No homelab services detected",
        )
    if down:
        return CheckResult(
            name="service_health",
            severity=CheckSeverity.WARNING,
            message=f"Services down: {', '.join(down)}",
            data={"down": down, "up": up, "total": total},
            recommendations=[f"Check: docker logs {down[0]}", "Restart the container"],
        )
    return CheckResult(
        name="service_health",
        severity=CheckSeverity.OK,
        message=f"All {total} services responding",
    )
