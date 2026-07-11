"""Tests for v2 code review fixes: metrics auth, settings allowlists, interface validation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_requires_auth(client: AsyncClient):
    """GET /metrics should require authentication."""
    response = await client.get("/metrics")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_metrics_accessible_with_auth(auth_client: AsyncClient):
    """GET /metrics should succeed when authenticated."""
    response = await auth_client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_ai_settings_rejects_unknown_keys(auth_client: AsyncClient):
    """PUT ai/settings should ignore unknown keys."""
    # First set a known key
    response = await auth_client.put(
        "/api/v1/system/ai/settings",
        json={"model": "claude-sonnet", "unknown_key": "malicious_value"},
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["model"] == "claude-sonnet"
    assert "unknown_key" not in settings


@pytest.mark.asyncio
async def test_ai_settings_accepts_valid_keys(auth_client: AsyncClient):
    """PUT ai/settings should accept all allowed keys."""
    response = await auth_client.put(
        "/api/v1/system/ai/settings",
        json={
            "provider": "anthropic",
            "model": "claude-sonnet",
            "temperature": 0.3,
            "max_tokens": 2048,
            "system_prompt": "test prompt",
            "context_options": {"include_system_metrics": False},
        },
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["provider"] == "anthropic"
    assert settings["model"] == "claude-sonnet"
    assert settings["temperature"] == 0.3
    assert settings["max_tokens"] == 2048
    assert settings["system_prompt"] == "test prompt"
    assert settings["context_options"]["include_system_metrics"] is False


@pytest.mark.asyncio
async def test_dns_settings_rejects_unknown_keys(auth_client: AsyncClient):
    """PUT dns should ignore unknown keys."""
    response = await auth_client.put(
        "/api/v1/network/dns",
        json={"primary": "9.9.9.9", "injected_key": "bad_value"},
    )
    assert response.status_code == 200
    config = response.json()["config"]
    assert config["primary"] == "9.9.9.9"
    assert "injected_key" not in config


@pytest.mark.asyncio
async def test_dns_settings_accepts_valid_keys(auth_client: AsyncClient):
    """PUT dns should accept all allowed keys."""
    response = await auth_client.put(
        "/api/v1/network/dns",
        json={
            "primary": "1.1.1.1",
            "secondary": "8.8.4.4",
            "search_domain": "test.local",
            "overrides": [{"host": "foo", "ip": "10.0.0.1"}],
        },
    )
    assert response.status_code == 200
    config = response.json()["config"]
    assert config["primary"] == "1.1.1.1"
    assert config["secondary"] == "8.8.4.4"
    assert config["search_domain"] == "test.local"
    assert len(config["overrides"]) == 1


@pytest.mark.asyncio
async def test_media_settings_rejects_unknown_keys(auth_client: AsyncClient):
    """PUT media/settings should ignore unknown keys."""
    response = await auth_client.put(
        "/api/v1/media/settings",
        json={"auto_rip": True, "evil_config": "/etc/shadow"},
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["auto_rip"] is True
    assert "evil_config" not in settings


@pytest.mark.asyncio
async def test_media_settings_accepts_valid_keys(auth_client: AsyncClient):
    """PUT media/settings should accept all allowed keys."""
    response = await auth_client.put(
        "/api/v1/media/settings",
        json={
            "auto_rip": True,
            "output_path": "/mnt/rips",
            "default_format": "mp4",
            "min_length_minutes": 20,
            "notifications": False,
        },
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["auto_rip"] is True
    assert settings["output_path"] == "/mnt/rips"
    assert settings["default_format"] == "mp4"
    assert settings["min_length_minutes"] == 20
    assert settings["notifications"] is False


@pytest.mark.asyncio
async def test_scrub_schedule_rejects_unknown_keys(auth_client: AsyncClient):
    """PUT scrubs/{pool} should ignore unknown keys."""
    response = await auth_client.put(
        "/api/v1/protection/scrubs/tank",
        json={"schedule": "monthly", "injected": "data"},
    )
    assert response.status_code == 200
    scrub = response.json()["scrub"]
    assert scrub["schedule"] == "monthly"
    assert "injected" not in scrub


@pytest.mark.asyncio
async def test_scrub_schedule_accepts_valid_keys(auth_client: AsyncClient):
    """PUT scrubs/{pool} should accept all allowed keys."""
    response = await auth_client.put(
        "/api/v1/protection/scrubs/mypool",
        json={
            "schedule": "daily",
            "last_run": 1700000000.0,
            "duration_seconds": 120,
            "errors": 0,
        },
    )
    assert response.status_code == 200
    scrub = response.json()["scrub"]
    assert scrub["schedule"] == "daily"
    assert scrub["pool"] == "mypool"
    assert scrub["last_run"] == 1700000000.0
    assert scrub["duration_seconds"] == 120
    assert scrub["errors"] == 0


@pytest.mark.asyncio
async def test_update_interface_validates_name(auth_client: AsyncClient):
    """PUT /network/interfaces/{name} should validate the name parameter."""
    # Invalid names with shell metacharacters should be rejected.
    # Some payloads (containing spaces/slashes) won't even match the route (405),
    # while others that match the route pattern get rejected by validation (400).
    response = await auth_client.put(
        "/api/v1/network/interfaces/eth0$(whoami)",
        json={"mtu": 1500},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_interface_accepts_valid_name(auth_client: AsyncClient):
    """PUT /network/interfaces/{name} should accept valid interface names."""
    response = await auth_client.put(
        "/api/v1/network/interfaces/eth0",
        json={"mtu": 1500},
    )
    assert response.status_code == 200
    assert response.json()["interface"] == "eth0"


@pytest.mark.asyncio
async def test_update_interface_rejects_shell_injection(auth_client: AsyncClient):
    """PUT /network/interfaces/{name} should reject shell injection payloads.

    Some payloads containing spaces/slashes will not match the route pattern
    and return 405. Payloads that match the route but contain shell metacharacters
    are rejected by _validate_shell_identifier with 400.
    """
    # Payloads that match the FastAPI route (single path segment, no spaces/slashes)
    single_segment_payloads = [
        "eth0$(whoami)",
        "wlan0`id`",
        "br0|cat",
    ]
    for payload in single_segment_payloads:
        response = await auth_client.put(
            f"/api/v1/network/interfaces/{payload}",
            json={"mtu": 9000},
        )
        assert response.status_code == 400, f"Should reject: {payload!r}"

    # Payloads with spaces/slashes never reach the handler (route mismatch)
    multi_segment_payloads = [
        "br0 && rm -rf /",
        "../../../etc/passwd",
    ]
    for payload in multi_segment_payloads:
        response = await auth_client.put(
            f"/api/v1/network/interfaces/{payload}",
            json={"mtu": 9000},
        )
        # These get 404 or 405 from the framework itself
        assert response.status_code in (400, 404, 405, 422), f"Should reject: {payload!r}"
