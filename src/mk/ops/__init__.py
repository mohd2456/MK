"""MK Proactive Operations — Autonomous infrastructure monitoring.

Transforms MK from reactive ("you ask, it answers") to proactive
("it watches, it alerts, it acts"). The ops layer runs continuously
in the background, executing scheduled checks and reacting to events.

Components:
    - Scheduler: Cron-like async scheduler with named intervals
    - CheckRegistry: Built-in health checks (containers, disk, certs, costs)
    - AlertManager: Routes alerts with severity, dedup, and cooldowns
    - EventBus: Event-driven reactions to system state changes

Usage:
    ops = OpsManager(alert_callback=send_telegram)
    ops.register_check(container_health_check)
    await ops.start()  # Runs forever in background
"""

from mk.ops.scheduler import Scheduler, ScheduleInterval, ScheduledJob
from mk.ops.checks import (
    Check,
    CheckResult,
    CheckSeverity,
    CheckRegistry,
    container_health,
    disk_prediction,
    backup_freshness,
    cert_expiry,
    cost_tracking,
    service_health,
    tailscale_health,
)
from mk.ops.alerts import AlertManager, Alert, AlertChannel, AlertState
from mk.ops.events import EventBus, Event, EventHandler
from mk.ops.manager import OpsManager

__all__ = [
    "Scheduler",
    "ScheduleInterval",
    "ScheduledJob",
    "Check",
    "CheckResult",
    "CheckSeverity",
    "CheckRegistry",
    "container_health",
    "disk_prediction",
    "backup_freshness",
    "cert_expiry",
    "cost_tracking",
    "service_health",
    "tailscale_health",
    "AlertManager",
    "Alert",
    "AlertChannel",
    "AlertState",
    "EventBus",
    "Event",
    "EventHandler",
    "OpsManager",
]
