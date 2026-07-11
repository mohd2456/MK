"""Integration tests for dashboard routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_summary(auth_client: AsyncClient):
    """Test dashboard summary returns system metrics."""
    response = await auth_client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    # Should have core metrics fields
    assert "cpu_percent" in data
    assert "ram_used_gb" in data
    assert "ram_total_gb" in data
    assert "ram_percent" in data
    assert "disk_used_tb" in data
    assert "disk_total_tb" in data
    assert "disk_percent" in data
    assert "uptime_seconds" in data
    assert "containers_running" in data
    assert "containers_total" in data
    # Values should be numeric
    assert isinstance(data["cpu_percent"], (int, float))
    assert isinstance(data["uptime_seconds"], (int, float))


@pytest.mark.asyncio
async def test_dashboard_alerts(auth_client: AsyncClient):
    """Test dashboard alerts returns a list."""
    response = await auth_client.get("/api/v1/dashboard/alerts")
    assert response.status_code == 200
    data = response.json()
    # Should be a list (may be empty without MK engine)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_dashboard_activity(auth_client: AsyncClient):
    """Test dashboard activity returns events."""
    response = await auth_client.get("/api/v1/dashboard/activity")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert isinstance(data["events"], list)


@pytest.mark.asyncio
async def test_dashboard_requires_auth(client: AsyncClient):
    """Test dashboard endpoints require authentication."""
    for path in [
        "/api/v1/dashboard/summary",
        "/api/v1/dashboard/alerts",
        "/api/v1/dashboard/activity",
    ]:
        response = await client.get(path)
        assert response.status_code == 401, f"{path} should require auth"
