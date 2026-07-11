"""Tests for input validation and shell injection prevention.

Verifies that endpoints with shell-interpolated path parameters
properly reject malicious input containing shell metacharacters.

Note: Some payloads (with spaces, slashes, newlines) are rejected at
the HTTP routing level (404/405) before they reach the handler. We test
URL-encoded variants that actually reach the handler and verify our
validation logic rejects them with 400.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# Payloads that contain shell metacharacters but form valid URL path segments
# (no unencoded slashes or spaces that would break routing).
# These reach the handler and must be rejected by our validator.
INJECTION_PAYLOADS = [
    "test$(whoami)",       # command substitution
    "name`id`",           # backtick command substitution
    "name>file",          # redirect
    "name<file",          # redirect
    'name"quoted',        # double quote
    "name'quoted",        # single quote
    "name\\backslash",    # backslash
    "a" * 200,            # too long (over 128 chars)
]

# Payloads that are encoded in the URL but decoded by FastAPI before
# reaching the handler. These test the actual injection vectors.
ENCODED_INJECTION_PAYLOADS = [
    "nginx;rm",           # semicolons (decoded from %3B by FastAPI)
    "test$(whoami)",      # dollar sign + parens
    "name`id`",          # backtick
    "a&&b",              # double ampersand
    "x|nc",              # pipe
]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTION_PAYLOADS + ENCODED_INJECTION_PAYLOADS)
async def test_service_start_rejects_injection(auth_client: AsyncClient, payload: str):
    """Service start endpoint rejects malicious service names."""
    response = await auth_client.post(f"/api/v1/system/services/{payload}/start")
    assert response.status_code == 400, f"Should reject: {payload!r}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTION_PAYLOADS + ENCODED_INJECTION_PAYLOADS)
async def test_service_stop_rejects_injection(auth_client: AsyncClient, payload: str):
    """Service stop endpoint rejects malicious service names."""
    response = await auth_client.post(f"/api/v1/system/services/{payload}/stop")
    assert response.status_code == 400, f"Should reject: {payload!r}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTION_PAYLOADS + ENCODED_INJECTION_PAYLOADS)
async def test_service_restart_rejects_injection(auth_client: AsyncClient, payload: str):
    """Service restart endpoint rejects malicious service names."""
    response = await auth_client.post(f"/api/v1/system/services/{payload}/restart")
    assert response.status_code == 400, f"Should reject: {payload!r}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTION_PAYLOADS + ENCODED_INJECTION_PAYLOADS)
async def test_eject_rejects_injection(auth_client: AsyncClient, payload: str):
    """Media eject endpoint rejects malicious device names."""
    response = await auth_client.post(f"/api/v1/media/eject/{payload}")
    assert response.status_code == 400, f"Should reject: {payload!r}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTION_PAYLOADS + ENCODED_INJECTION_PAYLOADS)
async def test_scrub_run_rejects_injection(auth_client: AsyncClient, payload: str):
    """Scrub run endpoint rejects malicious pool names."""
    response = await auth_client.post(f"/api/v1/protection/scrubs/{payload}/run")
    assert response.status_code == 400, f"Should reject: {payload!r}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTION_PAYLOADS + ENCODED_INJECTION_PAYLOADS)
async def test_container_restart_rejects_injection(auth_client: AsyncClient, payload: str):
    """Container restart endpoint rejects malicious container names."""
    response = await auth_client.post(f"/api/v1/apps/containers/{payload}/restart")
    assert response.status_code == 400, f"Should reject: {payload!r}, got {response.status_code}"


@pytest.mark.asyncio
async def test_updates_apply_rejects_malicious_packages(auth_client: AsyncClient):
    """Updates apply endpoint rejects malicious package names."""
    response = await auth_client.post(
        "/api/v1/system/updates/apply",
        json={"packages": ["valid-package", "; rm -rf /"]},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_updates_apply_rejects_empty_package_name(auth_client: AsyncClient):
    """Updates apply endpoint rejects empty package names."""
    response = await auth_client.post(
        "/api/v1/system/updates/apply",
        json={"packages": [""]},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_updates_apply_rejects_command_in_packages(auth_client: AsyncClient):
    """Updates apply endpoint rejects packages containing shell operators."""
    response = await auth_client.post(
        "/api/v1/system/updates/apply",
        json={"packages": ["nginx", "curl$(whoami)", "python3"]},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_valid_service_name_accepted(auth_client: AsyncClient):
    """Valid service names pass validation (may fail at systemctl level)."""
    # These are syntactically valid -- they will get past validation
    # but may fail at the systemctl level (which is fine, returns 500)
    response = await auth_client.post("/api/v1/system/services/nginx.service/start")
    # Should not be 400 (validation passes), may be 500 (no such service)
    assert response.status_code != 400

    response = await auth_client.post("/api/v1/system/services/my-service/stop")
    assert response.status_code != 400

    response = await auth_client.post("/api/v1/system/services/docker_daemon/restart")
    assert response.status_code != 400


@pytest.mark.asyncio
async def test_valid_device_name_accepted(auth_client: AsyncClient):
    """Valid device names pass validation."""
    response = await auth_client.post("/api/v1/media/eject/sr0")
    # Should not be 400 (validation passes)
    assert response.status_code != 400

    response = await auth_client.post("/api/v1/media/eject/cdrom1")
    assert response.status_code != 400


@pytest.mark.asyncio
async def test_valid_pool_name_accepted(auth_client: AsyncClient):
    """Valid pool names pass validation."""
    response = await auth_client.post("/api/v1/protection/scrubs/rpool/run")
    assert response.status_code != 400

    response = await auth_client.post("/api/v1/protection/scrubs/tank-data/run")
    assert response.status_code != 400


@pytest.mark.asyncio
async def test_valid_packages_accepted(auth_client: AsyncClient):
    """Valid package names pass validation."""
    response = await auth_client.post(
        "/api/v1/system/updates/apply",
        json={"packages": ["nginx", "curl", "python3.11", "lib++-dev"]},
    )
    # Should not be 400 (validation passes)
    assert response.status_code != 400


@pytest.mark.asyncio
async def test_disc_info_rejects_injection(auth_client: AsyncClient):
    """Disc info endpoint rejects malicious device names."""
    response = await auth_client.get("/api/v1/media/drives/sr0;whoami/disc")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_scrub_get_rejects_injection(auth_client: AsyncClient):
    """Scrub schedule GET endpoint rejects malicious pool names."""
    response = await auth_client.get("/api/v1/protection/scrubs/pool;rm/")
    # May be 400 or 307 redirect; check that the validated endpoint rejects it
    response = await auth_client.get("/api/v1/protection/scrubs/pool$(id)")
    assert response.status_code == 400
