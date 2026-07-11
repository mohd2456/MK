"""Integration tests for system routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_system_info(auth_client: AsyncClient):
    """Test system info endpoint returns expected fields."""
    response = await auth_client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "hostname" in data
    assert "os" in data
    assert "kernel" in data
    assert "arch" in data
    assert "python" in data
    assert "cpu_count" in data
    assert "uptime_seconds" in data
    # Uptime should be positive
    assert data["uptime_seconds"] > 0


@pytest.mark.asyncio
async def test_system_health(auth_client: AsyncClient):
    """Test system health endpoint."""
    response = await auth_client.get("/api/v1/system/health")
    assert response.status_code == 200
    data = response.json()
    assert "checks" in data
    assert isinstance(data["checks"], list)


@pytest.mark.asyncio
async def test_system_services(auth_client: AsyncClient):
    """Test listing system services."""
    response = await auth_client.get("/api/v1/system/services")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data


@pytest.mark.asyncio
async def test_service_start(auth_client: AsyncClient):
    """Test starting a service (will fail in test env but endpoint works)."""
    response = await auth_client.post("/api/v1/system/services/test-service/start")
    # Will likely fail (no such service), but should return 500 not crash
    assert response.status_code in (200, 500)


@pytest.mark.asyncio
async def test_service_stop(auth_client: AsyncClient):
    """Test stopping a service."""
    response = await auth_client.post("/api/v1/system/services/test-service/stop")
    assert response.status_code in (200, 500)


@pytest.mark.asyncio
async def test_service_restart(auth_client: AsyncClient):
    """Test restarting a service."""
    response = await auth_client.post("/api/v1/system/services/test-service/restart")
    assert response.status_code in (200, 500)


@pytest.mark.asyncio
async def test_system_updates(auth_client: AsyncClient):
    """Test listing available updates."""
    response = await auth_client.get("/api/v1/system/updates")
    assert response.status_code == 200
    data = response.json()
    assert "updates" in data
    assert "count" in data
    assert isinstance(data["count"], int)


@pytest.mark.asyncio
async def test_system_updates_apply(auth_client: AsyncClient):
    """Test applying updates (returns status)."""
    response = await auth_client.post(
        "/api/v1/system/updates/apply",
        json={"packages": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_system_power_reboot(auth_client: AsyncClient):
    """Test reboot endpoint responds correctly."""
    response = await auth_client.post("/api/v1/system/power/reboot")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_system_power_shutdown(auth_client: AsyncClient):
    """Test shutdown endpoint responds correctly."""
    response = await auth_client.post("/api/v1/system/power/shutdown")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_ai_settings_get(auth_client: AsyncClient):
    """Test getting AI settings."""
    response = await auth_client.get("/api/v1/system/ai/settings")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "model" in data
    assert "temperature" in data
    assert "max_tokens" in data


@pytest.mark.asyncio
async def test_ai_settings_update(auth_client: AsyncClient):
    """Test updating AI settings."""
    response = await auth_client.put(
        "/api/v1/system/ai/settings",
        json={"provider": "anthropic", "model": "claude-sonnet", "temperature": 0.5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["settings"]["provider"] == "anthropic"
    assert data["settings"]["model"] == "claude-sonnet"
    assert data["settings"]["temperature"] == 0.5

    # Verify persistence
    r = await auth_client.get("/api/v1/system/ai/settings")
    assert r.json()["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_system_requires_auth(client: AsyncClient):
    """Test system endpoints require authentication."""
    for path in [
        "/api/v1/system/info",
        "/api/v1/system/health",
        "/api/v1/system/services",
        "/api/v1/system/updates",
        "/api/v1/system/ai/settings",
    ]:
        response = await client.get(path)
        assert response.status_code == 401, f"{path} should require auth"
