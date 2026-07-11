"""Alert manager — routes notifications with dedup and cooldowns.

When a check produces a WARNING or CRITICAL result, the alert manager
decides whether and how to notify the user. It prevents alert fatigue by:
- Deduplicating: Same alert won't fire again while active
- Cooldowns: Minimum time between repeated alerts
- Escalation: Critical alerts bypass cooldowns
- Resolution: Notifies when an issue is resolved

Alerts are routed through configurable channels (Telegram, proactive queue,
log file) based on severity.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from mk.ops.checks import CheckResult, CheckSeverity

logger = logging.getLogger(__name__)


class AlertChannel(str, Enum):
    """Where alerts get delivered."""

    TELEGRAM = "telegram"  # Send via Telegram bot
    PROACTIVE = "proactive"  # Queue in proactive message system
    LOG = "log"  # Just log it (for INFO)
    SILENT = "silent"  # Suppress (acknowledged alerts)


class AlertState(str, Enum):
    """Lifecycle state of an alert."""

    FIRING = "firing"  # Active and unresolved
    ACKNOWLEDGED = "acknowledged"  # User saw it, still active
    RESOLVED = "resolved"  # Issue fixed
    SILENCED = "silenced"  # Manually silenced


@dataclass
class Alert:
    """A single alert instance.

    Tracks the full lifecycle from firing to resolution.
    """

    id: str
    check_name: str
    severity: CheckSeverity
    message: str
    state: AlertState = AlertState.FIRING
    channel: AlertChannel = AlertChannel.PROACTIVE
    fired_at: float = field(default_factory=time.time)
    last_notified: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    acknowledged_at: Optional[float] = None
    notification_count: int = 1
    data: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        """Whether this alert is still active (firing or acknowledged)."""
        return self.state in (AlertState.FIRING, AlertState.ACKNOWLEDGED)

    @property
    def duration_seconds(self) -> float:
        """How long this alert has been active."""
        end = self.resolved_at or time.time()
        return end - self.fired_at

    def format_notification(self) -> str:
        """Format the alert for user notification."""
        icon = {
            CheckSeverity.WARNING: "⚠️",
            CheckSeverity.CRITICAL: "🚨",
            CheckSeverity.INFO: "ℹ️",
        }.get(self.severity, "🔔")

        lines = [f"{icon} **{self.check_name}**: {self.message}"]

        if self.recommendations:
            lines.append("\nSuggested actions:")
            for rec in self.recommendations[:3]:
                lines.append(f"  → {rec}")

        return "\n".join(lines)

    def format_resolution(self) -> str:
        """Format the resolution notification."""
        duration = self.duration_seconds
        if duration < 60:
            dur_str = f"{duration:.0f}s"
        elif duration < 3600:
            dur_str = f"{duration / 60:.0f}m"
        else:
            dur_str = f"{duration / 3600:.1f}h"

        return f"✅ **{self.check_name}** resolved (was active for {dur_str})"


class AlertManager:
    """Manages alert lifecycle, routing, and deduplication.

    Key behaviors:
    - Same check can't fire a new alert while one is already active
    - Cooldown period between repeated notifications
    - Critical alerts always notify immediately
    - Sends resolution notifications when issues clear
    """

    def __init__(
        self,
        notify_callback: Optional[Callable[[str], Coroutine]] = None,
        default_cooldown_seconds: float = 1800.0,  # 30 minutes
        critical_cooldown_seconds: float = 300.0,  # 5 minutes for critical
    ) -> None:
        """Initialize the alert manager.

        Args:
            notify_callback: Async function to send notifications.
                Signature: async (message: str) -> None
            default_cooldown_seconds: Minimum time between repeat notifications.
            critical_cooldown_seconds: Cooldown for critical alerts (shorter).
        """
        self._notify = notify_callback
        self._default_cooldown = default_cooldown_seconds
        self._critical_cooldown = critical_cooldown_seconds
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._alert_counter: int = 0

    @property
    def active_count(self) -> int:
        """Number of currently active alerts."""
        return sum(1 for a in self._active_alerts.values() if a.is_active)

    @property
    def active_alerts(self) -> List[Alert]:
        """All currently active alerts."""
        return [a for a in self._active_alerts.values() if a.is_active]

    async def process_check_result(self, result: CheckResult) -> Optional[Alert]:
        """Process a check result and create/update/resolve alerts.

        This is the main entry point. Called after each check execution.

        Args:
            result: The check result to process.

        Returns:
            Alert if one was created or updated, None otherwise.
        """
        existing = self._active_alerts.get(result.name)

        if result.needs_alert:
            # Issue detected
            if existing and existing.is_active:
                # Already have an active alert — check cooldown for re-notification
                return await self._handle_repeat(existing, result)
            else:
                # New alert
                return await self._fire_new_alert(result)
        else:
            # Check is OK — resolve any active alert
            if existing and existing.is_active:
                await self._resolve_alert(existing)
            return None

    async def _fire_new_alert(self, result: CheckResult) -> Alert:
        """Create and fire a new alert.

        Args:
            result: The check result that triggered the alert.

        Returns:
            The created Alert.
        """
        self._alert_counter += 1
        alert_id = f"alert-{self._alert_counter:04d}"

        channel = self._route_channel(result.severity)

        alert = Alert(
            id=alert_id,
            check_name=result.name,
            severity=result.severity,
            message=result.message,
            channel=channel,
            data=result.data,
            recommendations=result.recommendations,
        )

        self._active_alerts[result.name] = alert

        # Send notification
        await self._send_notification(alert.format_notification(), channel)

        logger.info(f"Alert fired: [{result.severity.value}] {result.name}: {result.message}")
        return alert

    async def _handle_repeat(self, alert: Alert, result: CheckResult) -> Optional[Alert]:
        """Handle a repeated alert (same check still failing).

        Respects cooldown — won't spam the user.

        Args:
            alert: The existing active alert.
            result: The new check result.

        Returns:
            The alert if re-notified, None if cooldown suppressed it.
        """
        cooldown = (
            self._critical_cooldown
            if result.severity == CheckSeverity.CRITICAL
            else self._default_cooldown
        )

        time_since_last = time.time() - alert.last_notified

        if time_since_last >= cooldown:
            # Cooldown expired — re-notify
            alert.notification_count += 1
            alert.last_notified = time.time()
            alert.message = result.message  # Update message
            alert.data = result.data

            await self._send_notification(
                f"🔔 Still active ({alert.notification_count}x): {alert.format_notification()}",
                alert.channel,
            )
            return alert

        # Still in cooldown — suppress
        return None

    async def _resolve_alert(self, alert: Alert) -> None:
        """Resolve an active alert and notify."""
        alert.state = AlertState.RESOLVED
        alert.resolved_at = time.time()

        # Send resolution notification
        await self._send_notification(alert.format_resolution(), alert.channel)

        # Move to history
        self._alert_history.append(alert)
        if len(self._alert_history) > 200:
            self._alert_history = self._alert_history[-100:]

        logger.info(f"Alert resolved: {alert.check_name}")

    def acknowledge_alert(self, check_name: str) -> bool:
        """Acknowledge an alert (user saw it).

        Suppresses re-notifications but keeps the alert tracked.

        Args:
            check_name: The check name to acknowledge.

        Returns:
            True if found and acknowledged.
        """
        alert = self._active_alerts.get(check_name)
        if alert and alert.is_active:
            alert.state = AlertState.ACKNOWLEDGED
            alert.acknowledged_at = time.time()
            return True
        return False

    def silence_alert(self, check_name: str) -> bool:
        """Silence an alert (stop all notifications).

        Args:
            check_name: The check name to silence.

        Returns:
            True if found and silenced.
        """
        alert = self._active_alerts.get(check_name)
        if alert and alert.is_active:
            alert.state = AlertState.SILENCED
            return True
        return False

    def _route_channel(self, severity: CheckSeverity) -> AlertChannel:
        """Determine which channel to use for a severity level."""
        if severity == CheckSeverity.CRITICAL:
            return AlertChannel.TELEGRAM
        elif severity == CheckSeverity.WARNING:
            return AlertChannel.PROACTIVE
        else:
            return AlertChannel.LOG

    async def _send_notification(self, message: str, channel: AlertChannel) -> None:
        """Send a notification through the configured callback.

        Args:
            message: The notification text.
            channel: Target channel.
        """
        if channel == AlertChannel.LOG:
            logger.info(f"[Alert] {message}")
            return

        if channel == AlertChannel.SILENT:
            return

        if self._notify:
            try:
                await self._notify(message)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
        else:
            logger.info(f"[Alert:{channel.value}] {message}")

    def get_status(self) -> Dict[str, Any]:
        """Get alert manager status."""
        return {
            "active_alerts": self.active_count,
            "total_fired": self._alert_counter,
            "alerts": [
                {
                    "id": a.id,
                    "check": a.check_name,
                    "severity": a.severity.value,
                    "state": a.state.value,
                    "message": a.message,
                    "fired_at": a.fired_at,
                    "duration_seconds": a.duration_seconds,
                }
                for a in self._active_alerts.values()
                if a.is_active
            ],
        }
