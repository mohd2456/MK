"""Integration tests for media routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_drives(auth_client: AsyncClient):
    """Test listing optical drives."""
    response = await auth_client.get("/api/v1/media/drives")
    assert response.status_code == 200
    data = response.json()
    assert "drives" in data
    assert isinstance(data["drives"], list)


@pytest.mark.asyncio
async def test_disc_info(auth_client: AsyncClient):
    """Test getting disc info for a drive."""
    response = await auth_client.get("/api/v1/media/drives/sr0/disc")
    assert response.status_code == 200
    data = response.json()
    # Will show no disc or error since no physical drive
    assert "disc_present" in data or "error" in data


@pytest.mark.asyncio
async def test_rip_status(auth_client: AsyncClient):
    """Test getting rip status when no rip is active."""
    response = await auth_client.get("/api/v1/media/rip/status")
    assert response.status_code == 200
    data = response.json()
    assert "active" in data
    assert data["active"] is False


@pytest.mark.asyncio
async def test_start_rip(auth_client: AsyncClient):
    """Test starting a rip job."""
    response = await auth_client.post(
        "/api/v1/media/rip",
        json={"title": "Test Movie", "device": "/dev/sr0"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["title"] == "Test Movie"


@pytest.mark.asyncio
async def test_cancel_rip(auth_client: AsyncClient):
    """Test cancelling a rip."""
    # Start a rip first
    await auth_client.post(
        "/api/v1/media/rip",
        json={"title": "Test", "device": "/dev/sr0"},
    )
    # Cancel it
    response = await auth_client.post("/api/v1/media/rip/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_rip_when_none_active(auth_client: AsyncClient):
    """Test cancelling when no rip is active returns 409."""
    response = await auth_client.post("/api/v1/media/rip/cancel")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_eject_disc(auth_client: AsyncClient):
    """Test ejecting a disc (may fail without hardware)."""
    response = await auth_client.post("/api/v1/media/eject/sr0")
    # Will fail in test env (no drive), but endpoint should respond
    assert response.status_code in (200, 500)


@pytest.mark.asyncio
async def test_library_stats(auth_client: AsyncClient):
    """Test getting library statistics."""
    response = await auth_client.get("/api/v1/media/library/stats")
    assert response.status_code == 200
    data = response.json()
    assert "movies" in data
    assert "tv_shows" in data
    assert "total_size_bytes" in data


@pytest.mark.asyncio
async def test_recent_rips(auth_client: AsyncClient):
    """Test getting recent rip history."""
    response = await auth_client.get("/api/v1/media/rips/recent")
    assert response.status_code == 200
    data = response.json()
    assert "rips" in data
    assert isinstance(data["rips"], list)


@pytest.mark.asyncio
async def test_media_settings_get(auth_client: AsyncClient):
    """Test getting media settings."""
    response = await auth_client.get("/api/v1/media/settings")
    assert response.status_code == 200
    data = response.json()
    assert "auto_rip" in data
    assert "output_path" in data
    assert "default_format" in data


@pytest.mark.asyncio
async def test_media_settings_update(auth_client: AsyncClient):
    """Test updating media settings."""
    response = await auth_client.put(
        "/api/v1/media/settings",
        json={"auto_rip": True, "min_length_minutes": 15},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["settings"]["auto_rip"] is True
    assert data["settings"]["min_length_minutes"] == 15


@pytest.mark.asyncio
async def test_media_requires_auth(client: AsyncClient):
    """Test media endpoints require authentication."""
    for path in [
        "/api/v1/media/drives",
        "/api/v1/media/rip/status",
        "/api/v1/media/library/stats",
        "/api/v1/media/rips/recent",
        "/api/v1/media/settings",
    ]:
        response = await client.get(path)
        assert response.status_code == 401, f"{path} should require auth"
