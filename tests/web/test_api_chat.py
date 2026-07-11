"""Integration tests for the chat and context-suggestion routes.

These exercise the end-to-end wiring: the web API delegates to the MK
wrapper, which (with no engine supplied) lazily builds a safe default engine
running in command-only mode. The point is that the chat path is actually
wired through the engine and never returns the old "not initialized" stub.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_message_is_wired(auth_client: AsyncClient):
    """A chat message returns a real response, not the old stub."""
    response = await auth_client.post(
        "/api/v1/chat/message",
        json={"content": "hello", "context": {"path": "/"}},
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert data["content"]
    # The legacy stub used to return exactly this; it must be gone.
    assert data["content"] != "MK engine not initialized"
    assert "ok" in data


@pytest.mark.asyncio
async def test_chat_message_includes_context_actions(auth_client: AsyncClient):
    """Responses carry context-aware suggested actions."""
    response = await auth_client.post(
        "/api/v1/chat/message",
        json={"content": "hello", "context": {"path": "/storage"}},
    )
    assert response.status_code == 200
    data = response.json()
    labels = [s["label"] for s in data.get("suggestions", [])]
    assert "Disk temperatures" in labels


@pytest.mark.asyncio
async def test_chat_message_empty_content_rejected(auth_client: AsyncClient):
    """Empty content is a client error (422), not a 500."""
    response = await auth_client.post(
        "/api/v1/chat/message",
        json={"content": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_message_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/chat/message", json={"content": "hi"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_suggestions_endpoint(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/chat/suggestions", params={"path": "/network"})
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == "/network"
    assert data["context_label"] == "Network"
    prompts = [s["prompt"] for s in data["suggestions"]]
    assert any("WireGuard" in p for p in prompts)


@pytest.mark.asyncio
async def test_chat_suggestions_unknown_path_falls_back(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/chat/suggestions", params={"path": "/nope"})
    assert response.status_code == 200
    data = response.json()
    assert data["suggestions"]  # dashboard fallback, never empty


@pytest.mark.asyncio
async def test_chat_suggestions_limit(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/chat/suggestions", params={"path": "/", "limit": 2})
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 2


@pytest.mark.asyncio
async def test_chat_suggestions_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/chat/suggestions", params={"path": "/"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_history_empty_without_engine(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/chat/history")
    assert response.status_code == 200
    assert "messages" in response.json()
