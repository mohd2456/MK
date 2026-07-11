"""Self-health monitoring for MK.

Monitors the host system's resource usage (CPU, memory, disk)
and MK's own process health. Can generate alerts when resources
are running low.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class ResourceUsage(BaseModel):
    """System resource usage snapshot."""

    cpu_percent: float = Field(description="CPU usage percentage (0-100)")
    memory_total_mb: float = Field(description="Total system memory in MB")
    memory_used_mb: float = Field(description="Used system memory in MB")
    memory_percent: float = Field(description="Memory usage percentage (0-100)")
    disk_total_gb: float = Field(description="Total disk space in GB")
    disk_used_gb: float = Field(description="Used disk space in GB")
    disk_percent: float = Field(description="Disk usage percentage (0-100)")


class HealthReport(BaseModel):
    """Complete health report for MK and the host system."""

    healthy: bool = Field(description="Overall health status")
    timestamp: str = Field(description="ISO format timestamp of the check")
    resources: ResourceUsage = Field(description="Current resource usage")
    warnings: List[str] = Field(default_factory=list, description="Active warnings")
    uptime_seconds: float = Field(description="Process uptime in seconds")
    pid: int = Field(description="MK process ID")


@dataclass
class HealthMonitor:
    """Monitors MK's own health and the host system.

    Tracks CPU, memory, and disk usage, generating warnings
    when resources exceed configurable thresholds.

    Attributes:
        cpu_threshold: CPU usage percent to trigger warning.
        memory_threshold: Memory usage percent to trigger warning.
        disk_threshold: Disk usage percent to trigger warning.
    """

    cpu_threshold: float = 90.0
    memory_threshold: float = 85.0
    disk_threshold: float = 90.0

    def __post_init__(self) -> None:
        """Record the start time for uptime tracking."""
        self._start_time = time.time()

    def _get_cpu_percent(self) -> float:
        """Get CPU usage percentage.

        Uses /proc/loadavg on Linux as a lightweight approximation.
        Returns 0.0 if unable to read.
        """
        try:
            loadavg_path = Path("/proc/loadavg")
            if loadavg_path.exists():
                content = loadavg_path.read_text()
                load_1min = float(content.split()[0])
                cpu_count = os.cpu_count() or 1
                return min(100.0, (load_1min / cpu_count) * 100.0)
        except (OSError, ValueError):
            pass
        return 0.0

    def _get_memory_info(self) -> tuple:
        """Get memory usage from /proc/meminfo or fallback.

        Returns:
            Tuple of (total_mb, used_mb, percent).
        """
        try:
            meminfo_path = Path("/proc/meminfo")
            if meminfo_path.exists():
                info = {}
                content = meminfo_path.read_text()
                for line in content.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        value_kb = int(parts[1])
                        info[key] = value_kb

                total_kb = info.get("MemTotal", 0)
                available_kb = info.get("MemAvailable", info.get("MemFree", 0))
                used_kb = total_kb - available_kb

                total_mb = total_kb / 1024.0
                used_mb = used_kb / 1024.0
                percent = (used_kb / total_kb * 100.0) if total_kb > 0 else 0.0
                return (total_mb, used_mb, percent)
        except (OSError, ValueError):
            pass
        return (0.0, 0.0, 0.0)

    def _get_disk_info(self, path: str = "/") -> tuple:
        """Get disk usage for the given path.

        Args:
            path: Filesystem path to check.

        Returns:
            Tuple of (total_gb, used_gb, percent).
        """
        try:
            statvfs = os.statvfs(path)
            total = statvfs.f_frsize * statvfs.f_blocks
            free = statvfs.f_frsize * statvfs.f_bavail
            used = total - free

            total_gb = total / (1024**3)
            used_gb = used / (1024**3)
            percent = (used / total * 100.0) if total > 0 else 0.0
            return (total_gb, used_gb, percent)
        except OSError:
            return (0.0, 0.0, 0.0)

    def check_self_health(self) -> HealthReport:
        """Perform a complete health check.

        Checks CPU, memory, and disk usage against thresholds
        and generates warnings for any exceeded limits.

        Returns:
            HealthReport with current system status.
        """
        from datetime import datetime

        cpu_percent = self._get_cpu_percent()
        mem_total, mem_used, mem_percent = self._get_memory_info()
        disk_total, disk_used, disk_percent = self._get_disk_info()

        resources = ResourceUsage(
            cpu_percent=round(cpu_percent, 1),
            memory_total_mb=round(mem_total, 1),
            memory_used_mb=round(mem_used, 1),
            memory_percent=round(mem_percent, 1),
            disk_total_gb=round(disk_total, 1),
            disk_used_gb=round(disk_used, 1),
            disk_percent=round(disk_percent, 1),
        )

        warnings: List[str] = []
        if cpu_percent > self.cpu_threshold:
            warnings.append(
                f"CPU usage high: {cpu_percent:.1f}% (threshold: {self.cpu_threshold}%)"
            )
        if mem_percent > self.memory_threshold:
            warnings.append(
                f"Memory usage high: {mem_percent:.1f}% (threshold: {self.memory_threshold}%)"
            )
        if disk_percent > self.disk_threshold:
            warnings.append(
                f"Disk usage high: {disk_percent:.1f}% (threshold: {self.disk_threshold}%)"
            )

        uptime = time.time() - self._start_time
        healthy = len(warnings) == 0

        return HealthReport(
            healthy=healthy,
            timestamp=datetime.utcnow().isoformat(),
            resources=resources,
            warnings=warnings,
            uptime_seconds=round(uptime, 2),
            pid=os.getpid(),
        )

    def is_healthy(self) -> bool:
        """Quick health check - returns True if no warnings.

        Returns:
            True if all resource metrics are within thresholds.
        """
        report = self.check_self_health()
        return report.healthy
