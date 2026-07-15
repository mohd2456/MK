"""Tests for the proactive notification system (ops → broadcaster → WS)."""

from __future__ import annotations

import pytest

from mk.ops.alerts import AlertManager
from mk.ops.checks import CheckResult, CheckSeverity
from mk.ops.notifications import NotificationBroadcaster
from mk.ops.real_checks import real_container_health, real_disk_health


@pytest.mark.asyncio
async def test_broadcaster_delivers_to_callback():
    """The broadcaster calls its notify_callback and counts."""
    received = []

    async def sink(msg: str):
        received.append(msg)

    # Use a simulated broadcaster (no real WS)
    b = NotificationBroadcaster(telegram_send=sink)
    await b.notify("hello world")
    assert received == ["hello world"]
    assert b.notification_count == 1


@pytest.mark.asyncio
async def test_alert_manager_fires_through_broadcaster():
    """A failing check result → alert fired → broadcaster receives message."""
    messages = []

    async def sink(msg: str):
        messages.append(msg)

    broadcaster = NotificationBroadcaster(telegram_send=sink)
    am = AlertManager(notify_callback=broadcaster.notify)

    result = CheckResult(
        name="disk_health",
        severity=CheckSeverity.CRITICAL,
        message="Root filesystem 98% full",
        recommendations=["Free space NOW"],
    )
    alert = await am.process_check_result(result)
    assert alert is not None
    assert alert.state.value == "firing"
    assert len(messages) == 1
    assert "disk_health" in messages[0]
    assert "98%" in messages[0]


@pytest.mark.asyncio
async def test_alert_resolves_and_notifies():
    """When a check returns OK after firing, the alert resolves + notifies."""
    messages = []

    async def sink(msg: str):
        messages.append(msg)

    broadcaster = NotificationBroadcaster(telegram_send=sink)
    am = AlertManager(notify_callback=broadcaster.notify)

    # Fire
    bad = CheckResult(name="svc", severity=CheckSeverity.WARNING, message="down")
    await am.process_check_result(bad)
    assert len(messages) == 1

    # Resolve
    good = CheckResult(name="svc", severity=CheckSeverity.OK, message="up")
    await am.process_check_result(good)
    assert len(messages) == 2
    assert "resolved" in messages[1]


@pytest.mark.asyncio
async def test_real_container_check_runs():
    """The real container check executes without crashing (even without Docker)."""
    result = await real_container_health()
    assert result.name == "container_health"
    assert result.severity in (CheckSeverity.OK, CheckSeverity.WARNING, CheckSeverity.CRITICAL)


@pytest.mark.asyncio
async def test_real_disk_check_runs():
    """The real disk check executes without crashing."""
    result = await real_disk_health()
    assert result.name == "disk_health"
    assert result.severity in (CheckSeverity.OK, CheckSeverity.WARNING, CheckSeverity.CRITICAL)


@pytest.mark.asyncio
async def test_broadcaster_increments_metrics():
    """Each notification increments mk_notifications_total."""
    from mk.metrics import metrics

    before = metrics.get_counter("mk_notifications_total")
    b = NotificationBroadcaster()
    await b.notify("test")
    assert metrics.get_counter("mk_notifications_total") == before + 1
