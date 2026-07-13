"""Shared fixtures for web API integration tests."""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mk.web import app as web_app
from mk.web.app import create_app

TEST_PIN = "1234"


@pytest_asyncio.fixture(autouse=True)
async def _close_chat_history():
    """Close the persistent chat-history store after each test.

    The store keeps a long-lived (non-daemon) aiosqlite connection open on
    first use; closing it here prevents connection threads from leaking and
    keeps the test process able to exit cleanly.
    """
    yield
    store = getattr(web_app, "_chat_history", None)
    if store is not None:
        await store.close()


@pytest.fixture
def app(tmp_path):
    """Create a fresh FastAPI app for testing.

    The audit trail is pointed at a per-test temp directory so security
    audit entries never leak between tests or into the developer's ~/.mk.
    """
    return create_app(
        pin=TEST_PIN,
        audit_log_dir=str(tmp_path / "audit"),
        enable_backup_scheduling=False,  # no systemd/sudo side effects in tests
    )


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated client (login already done)."""
    response = await client.post("/api/v1/auth/login", json={"pin": TEST_PIN})
    assert response.status_code == 200
    token = response.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
