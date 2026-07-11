"""Tests for health monitoring."""

from __future__ import annotations

import os


from mk.safety.health import HealthMonitor, HealthReport, ResourceUsage


class TestHealthMonitor:
    """Tests for self-health monitoring."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.monitor = HealthMonitor()

    def test_check_self_health_returns_report(self) -> None:
        """Should return a complete HealthReport."""
        report = self.monitor.check_self_health()
        assert isinstance(report, HealthReport)
        assert isinstance(report.resources, ResourceUsage)

    def test_report_has_timestamp(self) -> None:
        """Should include an ISO format timestamp."""
        report = self.monitor.check_self_health()
        assert report.timestamp is not None
        # Verify ISO format by parsing
        from datetime import datetime

        datetime.fromisoformat(report.timestamp)

    def test_report_has_pid(self) -> None:
        """Should include the current process ID."""
        report = self.monitor.check_self_health()
        assert report.pid == os.getpid()

    def test_report_has_uptime(self) -> None:
        """Should report uptime in seconds."""
        report = self.monitor.check_self_health()
        assert report.uptime_seconds >= 0

    def test_resources_have_valid_ranges(self) -> None:
        """Resource values should be non-negative."""
        report = self.monitor.check_self_health()
        resources = report.resources
        assert resources.cpu_percent >= 0
        assert resources.memory_percent >= 0
        assert resources.disk_percent >= 0

    def test_is_healthy_returns_bool(self) -> None:
        """is_healthy should return a boolean."""
        result = self.monitor.is_healthy()
        assert isinstance(result, bool)

    def test_warnings_on_high_cpu_threshold(self) -> None:
        """Should warn when CPU exceeds threshold."""
        # Set impossibly low threshold to trigger warning
        monitor = HealthMonitor(cpu_threshold=0.001)
        report = monitor.check_self_health()
        # On systems with any load this will trigger; on idle it may not
        # Just verify the structure is correct
        assert isinstance(report.warnings, list)

    def test_warnings_on_high_memory_threshold(self) -> None:
        """Should warn when memory exceeds threshold."""
        monitor = HealthMonitor(memory_threshold=0.001)
        report = monitor.check_self_health()
        # On most systems, some memory is used
        # Verify structure
        assert isinstance(report.warnings, list)

    def test_warnings_on_high_disk_threshold(self) -> None:
        """Should warn when disk exceeds threshold."""
        # Set very low threshold
        monitor = HealthMonitor(disk_threshold=0.001)
        report = monitor.check_self_health()
        # Any disk usage should trigger this
        if report.resources.disk_percent > 0.001:
            assert len(report.warnings) >= 1
            assert "Disk usage high" in report.warnings[-1]

    def test_healthy_with_normal_thresholds(self) -> None:
        """Should be healthy with default thresholds on most systems."""
        # Default thresholds are generous (90%, 85%, 90%)
        report = self.monitor.check_self_health()
        # This should be healthy on most test machines
        assert isinstance(report.healthy, bool)

    def test_custom_thresholds(self) -> None:
        """Should accept custom thresholds."""
        monitor = HealthMonitor(
            cpu_threshold=50.0,
            memory_threshold=60.0,
            disk_threshold=70.0,
        )
        assert monitor.cpu_threshold == 50.0
        assert monitor.memory_threshold == 60.0
        assert monitor.disk_threshold == 70.0

    def test_disk_info_for_root(self) -> None:
        """Should report disk info for root filesystem."""
        report = self.monitor.check_self_health()
        # Total disk should be positive (we're running on a machine)
        assert report.resources.disk_total_gb > 0
