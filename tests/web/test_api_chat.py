"""Integration tests for the chat + suggestions API wired through MKWrapper."""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mk.web.app import create_app

TEST_PIN = "1234"


class _FakeResponse:
    def __init__(self, text, provider=None, direct=False):
        self.final_response = text
        self.provider_used = provider
        self.tokens_used = 3
        self.cost = 0.0
        self.was_direct_command = direct


class _FakeEngine:
    """Engine double that echoes input through the wrapper path."""

    def __init__(self, text="Handled.", provider="openai", direct=False, exc=None):
        self._text = text
        self._provider = provider
        self._direct = direct
        self._exc = exc

    async def process(self, user_input):
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(f"{self._text} ({user_input})", self._provider, self._direct)


async def _login(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/login", json={"pin": TEST_PIN})
    assert resp.status_code == 200
    client.headers["Authorization"] = f"Bearer {resp.json()['token']}"


@pytest_asyncio.fixture
async def engine_client() -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client backed by a healthy fake engine."""
    app = create_app(mk_engine=_FakeEngine(), pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await _login(ac)
        yield ac


@pytest_asyncio.fixture
async def no_engine_client() -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with NO engine wired in."""
    app = create_app(pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await _login(ac)
        yield ac


@pytest.mark.asyncio
async def test_chat_message_requires_auth():
    app = create_app(mk_engine=_FakeEngine(), pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/chat/message", json={"content": "hi"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_message_success(engine_client: AsyncClient):
    resp = await engine_client.post(
        "/api/v1/chat/message",
        json={"content": "status", "context": {"page": "/dashboard"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "status" in data["content"]
    assert data["provider"] == "openai"
    assert data["failure_type"] is None
    assert len(data["suggestions"]) > 0
    assert data["suggestions"][0]["id"] == "dash.status"


@pytest.mark.asyncio
async def test_chat_message_empty_content_returns_422(engine_client: AsyncClient):
    resp = await engine_client.post("/api/v1/chat/message", json={"content": "   "})
    assert resp.status_code == 422
    assert "content" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_message_no_engine_graceful(no_engine_client: AsyncClient):
    resp = await no_engine_client.post("/api/v1/chat/message", json={"content": "hi"})
    # Graceful degradation, NOT a 500.
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["failure_type"] == "no_engine"
    assert data["degraded"] is True
    assert data["content"]  # user-facing message present


@pytest.mark.asyncio
async def test_chat_message_engine_error_no_500():
    app = create_app(mk_engine=_FakeEngine(exc=RuntimeError("kaboom")), pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await _login(ac)
        resp = await ac.post("/api/v1/chat/message", json={"content": "hi"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["failure_type"] == "engine_error"
        assert data["retryable"] is True


@pytest.mark.asyncio
async def test_chat_message_context_drives_suggestions(engine_client: AsyncClient):
    resp = await engine_client.post(
        "/api/v1/chat/message",
        json={"content": "hi", "context": {"page": "/storage"}},
    )
    data = resp.json()
    assert any(s["category"] == "storage" for s in data["suggestions"])


@pytest.mark.asyncio
async def test_suggestions_endpoint(engine_client: AsyncClient):
    resp = await engine_client.get("/api/v1/chat/suggestions", params={"page": "/network"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == "/network"
    assert len(data["suggestions"]) > 0
    assert all("command" in s for s in data["suggestions"])


@pytest.mark.asyncio
async def test_suggestions_endpoint_with_selection(engine_client: AsyncClient):
    resp = await engine_client.get(
        "/api/v1/chat/suggestions",
        params={"page": "/apps", "selection": "plex"},
    )
    data = resp.json()
    assert data["suggestions"][0]["id"] == "context.inspect_selection"
    assert "plex" in data["suggestions"][0]["command"]


@pytest.mark.asyncio
async def test_suggestions_endpoint_requires_auth():
    app = create_app(mk_engine=_FakeEngine(), pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/chat/suggestions", params={"page": "/"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_stub_message_is_gone(no_engine_client: AsyncClient):
    """The legacy 'MK engine not initialized' stub must no longer appear."""
    resp = await no_engine_client.post("/api/v1/chat/message", json={"content": "hi"})
    assert "not initialized" not in resp.json()["content"]
