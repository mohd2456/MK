"""Ops Manager — Orchestrates all proactive operations.

The OpsManager is the top-level entry point for MK's autonomous
infrastructure monitoring. It ties together:
- Scheduler: runs checks on their configured intervals
- CheckRegistry: the library of health checks
- AlertManager: routes and deduplicates notifications
- EventBus: reactive event-driven automation

On startup, it registers the built-in checks, hooks them into
the scheduler, and starts the event bus. From that point on,
MK is actively watching the infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from mk.ops.alerts import AlertManager, Alert
from mk.ops.checks import (
    Check,
    CheckRegistry,
    CheckResult,
    CheckSeverity,
    backup_freshness,
    cert_expiry,
    container_health,
    cost_tracking,
    disk_prediction,
    service_health,
    tailscale_health,
)
from mk.ops.events import Event, EventBus
from mk.ops.scheduler import ScheduleInterval, Scheduler

logger = logging.getLogger(__name__)


class OpsManager:
    """Orchestrates MK's proactive infrastructure monitoring.

    This is what makes MK feel like an OS instead of a chatbot.
    It runs continuously, checks things, alerts on issues, and
    can auto-remediate known problems.

    Lifecycle:
        manager = OpsManager(notify_callback=send_telegram)
        await manager.start()
        # ... runs forever in background ...
        await manager.stop()
    """

    def __init__(
        self,
        notify_callback: Optional[Callable[[str], Coroutine]] = None,
        register_defaults: bool = True,
    ) -> None:
        """Initialize the ops manager.

        Args:
            notify_callback: Async function for sending notifications
                to the user. Signature: async (message: str) -> None
            register_defaults: Whether to register built-in checks.
        """
        self.scheduler = Scheduler()
        self.checks = CheckRegistry()
        self.alerts = AlertManager(notify_callback=notify_callback)
        self.events = EventBus()

        self._started = False
        self._started_at: Optional[float] = None
        self._notify = notify_callback

        if register_defaults:
            self._register_default_checks()
            self._register_default_events()

    @property
    def is_running(self) -> bool:
        """Whether the ops manager is active."""
        return self._started

    def _register_default_checks(self) -> None:
        """Register all built-in health checks with appropriate schedules."""

        # Container health — every 5 minutes
        self.checks.register(
            name="container_health",
            handler=container_health,
            description="Docker container status and restart detection",
            category="containers",
        )
        self.scheduler.register(
            name="check:container_health",
            handler=self._wrap_check("container_health"),
            interval=ScheduleInterval.EVERY_5_MINUTES,
            description="Container health check",
            jitter_seconds=30,
        )

        # Disk prediction — hourly
        self.checks.register(
            name="disk_prediction",
            handler=disk_prediction,
            description="Disk usage trend analysis and fill prediction",
            category="storage",
        )
        self.scheduler.register(
            name="check:disk_prediction",
            handler=self._wrap_check("disk_prediction"),
            interval=ScheduleInterval.HOURLY,
            description="Disk capacity prediction",
            jitter_seconds=120,
        )

        # Backup freshness — every 6 hours
        self.checks.register(
            name="backup_freshness",
            handler=backup_freshness,
            description="Backup age verification",
            category="backup",
        )
        self.scheduler.register(
            name="check:backup_freshness",
            handler=self._wrap_check("backup_freshness"),
            interval=ScheduleInterval.EVERY_6_HOURS,
            description="Backup freshness check",
            jitter_seconds=300,
        )

        # Certificate expiry — daily
        self.checks.register(
            name="cert_expiry",
            handler=cert_expiry,
            description="TLS certificate expiration monitoring",
            category="security",
        )
        self.scheduler.register(
            name="check:cert_expiry",
            handler=self._wrap_check("cert_expiry"),
            interval=ScheduleInterval.DAILY,
            description="Certificate expiry check",
            jitter_seconds=600,
        )

        # Cost tracking — daily
        self.checks.register(
            name="cost_tracking",
            handler=cost_tracking,
            description="LLM API cost monitoring",
            category="costs",
        )
        self.scheduler.register(
            name="check:cost_tracking",
            handler=self._wrap_check("cost_tracking"),
            interval=ScheduleInterval.DAILY,
            description="LLM cost tracking",
            jitter_seconds=300,
        )

        # Service health — every 5 minutes
        self.checks.register(
            name="service_health",
            handler=service_health,
            description="HTTP service availability",
            category="services",
        )
        self.scheduler.register(
            name="check:service_health",
            handler=self._wrap_check("service_health"),
            interval=ScheduleInterval.EVERY_5_MINUTES,
            description="Service health pings",
            jitter_seconds=15,
        )

        # Tailscale — every 15 minutes
        self.checks.register(
            name="tailscale_health",
            handler=tailscale_health,
            description="Tailscale VPN connection and peer status",
            category="network",
        )
        self.scheduler.register(
            name="check:tailscale_health",
            handler=self._wrap_check("tailscale_health"),
            interval=ScheduleInterval.EVERY_15_MINUTES,
            description="Tailscale connection health",
            jitter_seconds=30,
        )

    def _register_default_events(self) -> None:
        """Register default event handlers."""

        # When a check fails, emit an event
        # (Other systems can subscribe to check failures)

        # Container restart event → auto-investigate
        async def on_container_restart(event: Event) -> None:
            container = event.data.get("name", "unknown")
            count = event.data.get("count", 1)
            if count >= 3:
                msg = f"🔄 Container '{container}' has restarted {count}x — investigating"
                if self._notify:
                    await self._notify(msg)

        self.events.subscribe(
            name="container_restart_handler",
            pattern="container:restart",
            handler=on_container_restart,
            description="Alert on excessive container restarts",
            cooldown_seconds=300,
        )

        # Schedule events (emitted by scheduler for plugin triggers)
        async def on_schedule_event(event: Event) -> None:
            logger.debug(f"Schedule event: {event.type}")

        self.events.subscribe(
            name="schedule_logger",
            pattern="schedule:*",
            handler=on_schedule_event,
            description="Log schedule events",
        )

    def _wrap_check(self, check_name: str) -> Callable:
        """Wrap a health check into a scheduler-compatible handler.

        The wrapper runs the check AND processes the result through
        the alert manager.

        Args:
            check_name: Name of the check to wrap.

        Returns:
            Async function suitable for the scheduler.
        """

        async def wrapped() -> str:
            check = self.checks.get_check(check_name)
            if not check:
                return f"Check '{check_name}' not found"

            result = await check.run()

            # Route through alert manager
            await self.alerts.process_check_result(result)

            # Emit event if check failed
            if result.needs_alert:
                await self.events.emit_simple(
                    f"check:failed",
                    source="ops",
                    check=check_name,
                    severity=result.severity.value,
                    message=result.message,
                )

            return result.message

        return wrapped

    async def start(self) -> None:
        """Start the ops manager.

        Begins the scheduler, which runs all checks on their intervals.
        This runs in the background — returns immediately.
        """
        if self._started:
            return

        self._started = True
        self._started_at = time.time()
        await self.scheduler.start()

        logger.info(
            f"OpsManager started: {self.checks.check_count} checks, "
            f"{self.scheduler.job_count} scheduled jobs, "
            f"{self.events.handler_count} event handlers"
        )

    async def stop(self) -> None:
        """Stop the ops manager gracefully."""
        self._started = False
        await self.scheduler.stop()
        logger.info("OpsManager stopped")

    async def run_all_checks_now(self) -> List[CheckResult]:
        """Run all checks immediately (bypass scheduler).

        Useful for on-demand health reports.

        Returns:
            List of all check results.
        """
        results = await self.checks.run_all()

        # Process through alerts
        for result in results:
            await self.alerts.process_check_result(result)

        return results

    def register_check(
        self,
        name: str,
        handler: Callable[..., Coroutine],
        interval: ScheduleInterval | int,
        description: str = "",
        category: str = "custom",
    ) -> None:
        """Register a custom health check.

        Args:
            name: Check name.
            handler: Async function returning CheckResult.
            interval: How often to run.
            description: Description.
            category: Category for grouping.
        """
        self.checks.register(name, handler, description, category)
        self.scheduler.register(
            name=f"check:{name}",
            handler=self._wrap_check(name),
            interval=interval,
            description=description,
        )

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive ops status."""
        return {
            "running": self._started,
            "uptime_seconds": time.time() - self._started_at if self._started_at else 0,
            "checks": {
                "total": self.checks.check_count,
                "last_results": [
                    {
                        "name": r.name,
                        "severity": r.severity.value,
                        "message": r.message,
                    }
                    for r in self.checks.get_all_results()
                ],
            },
            "scheduler": self.scheduler.get_status(),
            "alerts": self.alerts.get_status(),
            "events": self.events.get_status(),
        }

    def health_report(self) -> str:
        """Generate a formatted health report from latest check results."""
        results = self.checks.get_all_results()
        if not results:
            return "No check results yet — checks haven't run."

        lines = ["📊 **MK Health Report**\n"]

        ok_count = sum(1 for r in results if r.is_ok)
        warn_count = sum(1 for r in results if r.severity == CheckSeverity.WARNING)
        crit_count = sum(1 for r in results if r.severity == CheckSeverity.CRITICAL)

        lines.append(f"Overall: {ok_count} OK, {warn_count} warnings, {crit_count} critical\n")

        for result in sorted(results, key=lambda r: r.severity.value, reverse=True):
            lines.append(result.format())

        if self.alerts.active_count > 0:
            lines.append(f"\n🔔 Active alerts: {self.alerts.active_count}")

        return "\n".join(lines)
