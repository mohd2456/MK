"""Shared fixtures for web API integration tests."""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mk.web.app import create_app

TEST_PIN = "1234"


@pytest.fixture
def app():
    """Create a fresh FastAPI app for testing."""
    return create_app(pin=TEST_PIN)


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
