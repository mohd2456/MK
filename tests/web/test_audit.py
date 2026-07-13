"""Tests for the web API security audit trail.

Verifies that state-changing API calls and login outcomes are recorded and
surfaced through the dashboard activity endpoint, and that request bodies
(which may contain secrets) are never persisted.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success_is_audited(auth_client: AsyncClient):
    """A successful login (performed by the auth_client fixture) is recorded."""
    resp = await auth_client.get("/api/v1/dashboard/activity")
    assert resp.status_code == 200
    events = resp.json()["events"]
    login_events = [e for e in events if e["action"] == "auth.login"]
    assert login_events, "expected an auth.login audit entry"
    assert login_events[0]["success"] is True
    assert login_events[0]["result"] == "success"


@pytest.mark.asyncio
async def test_failed_login_is_audited(client: AsyncClient):
    """A failed login is recorded as an unsuccessful auth.login event."""
    bad = await client.post("/api/v1/auth/login", json={"pin": "0000"})
    assert bad.status_code == 401

    # Authenticate properly to read the activity log.
    good = await client.post("/api/v1/auth/login", json={"pin": "1234"})
    token = good.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.get("/api/v1/dashboard/activity")
    events = resp.json()["events"]
    failures = [e for e in events if e["action"] == "auth.login" and e["success"] is False]
    assert failures, "expected a failed auth.login audit entry"
    assert failures[0]["result"] == "invalid_pin"


@pytest.mark.asyncio
async def test_mutating_request_is_audited(auth_client: AsyncClient):
    """A POST/PUT to a mutating endpoint appears in the audit trail."""
    # This updates AI settings (a mutating PUT). It should be audited
    # regardless of the underlying result.
    await auth_client.put(
        "/api/v1/system/ai/settings",
        json={"provider": "openai", "model": "gpt-5.4-mini"},
    )

    resp = await auth_client.get("/api/v1/dashboard/activity")
    events = resp.json()["events"]
    http_events = [e for e in events if e["action"].startswith("http.")]
    assert http_events, "expected an http.* audit entry for the mutating call"
    paths = [e["params"].get("path") for e in http_events]
    assert "/api/v1/system/ai/settings" in paths


@pytest.mark.asyncio
async def test_audit_does_not_record_request_bodies(auth_client: AsyncClient):
    """Audit entries must not contain request bodies (no leaked secrets)."""
    await auth_client.put(
        "/api/v1/system/ai/settings",
        json={"provider": "openai", "model": "secret-model-name-xyz"},
    )
    resp = await auth_client.get("/api/v1/dashboard/activity")
    events = resp.json()["events"]
    # The only recorded params should be the path — never the JSON body.
    for e in events:
        assert "secret-model-name-xyz" not in str(e)


@pytest.mark.asyncio
async def test_get_requests_are_not_audited(auth_client: AsyncClient):
    """Read-only GET requests should not create http.* audit entries."""
    await auth_client.get("/api/v1/system/info")
    await auth_client.get("/api/v1/storage/pools")

    resp = await auth_client.get("/api/v1/dashboard/activity")
    events = resp.json()["events"]
    get_events = [
        e
        for e in events
        if e["action"].startswith("http.")
        and e["params"].get("path") in ("/api/v1/system/info", "/api/v1/storage/pools")
    ]
    assert not get_events, "GET requests must not be audited"
