"""Tests for the persistent chat-history store and the history endpoint."""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mk.web.app import create_app
from mk.web.chat_history import ChatHistoryStore

TEST_PIN = "1234"


# ── Unit tests: ChatHistoryStore ────────────────────────────────────────


@pytest_asyncio.fixture
async def store() -> AsyncGenerator[ChatHistoryStore, None]:
    s = ChatHistoryStore(db_path=":memory:", max_messages_per_session=5)
    try:
        yield s
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_append_and_get_in_order(store: ChatHistoryStore):
    await store.append("s1", "user", "hello")
    await store.append("s1", "assistant", "hi there")
    msgs = await store.get_messages("s1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert [m["content"] for m in msgs] == ["hello", "hi there"]


@pytest.mark.asyncio
async def test_failure_metadata_round_trip(store: ChatHistoryStore):
    await store.append(
        "s1",
        "assistant",
        "That took too long.",
        ok=False,
        failure_type="timeout",
    )
    msg = (await store.get_messages("s1"))[0]
    assert msg["ok"] is False
    assert msg["failure_type"] == "timeout"


@pytest.mark.asyncio
async def test_actions_round_trip(store: ChatHistoryStore):
    actions = [{"label": "Open", "action": "navigate", "target": "/storage"}]
    await store.append("s1", "assistant", "see storage", actions=actions)
    msg = (await store.get_messages("s1"))[0]
    assert msg["actions"] == actions


@pytest.mark.asyncio
async def test_sessions_are_isolated(store: ChatHistoryStore):
    await store.append("a", "user", "in a")
    await store.append("b", "user", "in b")
    assert len(await store.get_messages("a")) == 1
    assert (await store.get_messages("a"))[0]["content"] == "in a"
    assert (await store.get_messages("b"))[0]["content"] == "in b"


@pytest.mark.asyncio
async def test_pruning_keeps_only_recent(store: ChatHistoryStore):
    # max_messages_per_session=5; write 8, expect the last 5 retained.
    for i in range(8):
        await store.append("s1", "user", f"msg-{i}")
    msgs = await store.get_messages("s1", limit=100)
    assert len(msgs) == 5
    assert [m["content"] for m in msgs] == [f"msg-{i}" for i in range(3, 8)]


@pytest.mark.asyncio
async def test_get_limit_returns_most_recent(store: ChatHistoryStore):
    for i in range(5):
        await store.append("s1", "user", f"m{i}")
    msgs = await store.get_messages("s1", limit=2)
    assert [m["content"] for m in msgs] == ["m3", "m4"]


@pytest.mark.asyncio
async def test_clear(store: ChatHistoryStore):
    await store.append("s1", "user", "hello")
    await store.clear("s1")
    assert await store.get_messages("s1") == []


@pytest.mark.asyncio
async def test_unknown_session_is_empty(store: ChatHistoryStore):
    assert await store.get_messages("nope") == []


@pytest.mark.asyncio
async def test_empty_session_id_is_noop(store: ChatHistoryStore):
    await store.append("", "user", "ignored")
    assert await store.get_messages("") == []


@pytest.mark.asyncio
async def test_close_is_idempotent(store: ChatHistoryStore):
    await store.append("s1", "user", "hi")
    await store.close()
    await store.close()  # must not raise


# ── Integration tests: history endpoint end-to-end ──────────────────────


class _FakeEngine:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc

    async def process(self, user_input: str):
        if self._exc is not None:
            raise self._exc

        class R:
            final_response = f"Reply: {user_input}"
            provider_used = "openai"
            tokens_used = 2
            cost = 0.0
            was_direct_command = False

        return R()


@pytest_asyncio.fixture
async def engine_client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app(mk_engine=_FakeEngine(), pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"pin": TEST_PIN})
        ac.headers["Authorization"] = f"Bearer {resp.json()['token']}"
        yield ac


@pytest.mark.asyncio
async def test_messages_persist_and_load_by_session(engine_client: AsyncClient):
    sid = "sess-persist"
    await engine_client.post(
        "/api/v1/chat/message",
        json={"content": "hello", "context": {"page": "/dashboard"}, "session_id": sid},
    )
    await engine_client.post(
        "/api/v1/chat/message",
        json={"content": "again", "context": {"page": "/storage"}, "session_id": sid},
    )
    resp = await engine_client.get("/api/v1/chat/history", params={"session_id": sid})
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    # 2 user + 2 assistant, in order.
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["content"] == "Reply: hello"


@pytest.mark.asyncio
async def test_history_is_isolated_per_session(engine_client: AsyncClient):
    await engine_client.post(
        "/api/v1/chat/message",
        json={"content": "in one", "context": {}, "session_id": "one"},
    )
    resp = await engine_client.get("/api/v1/chat/history", params={"session_id": "two"})
    # Session "two" has no persisted messages; engine has no conversation attr.
    assert resp.json()["messages"] == []


@pytest.mark.asyncio
async def test_failure_reply_is_persisted():
    app = create_app(mk_engine=_FakeEngine(exc=RuntimeError("boom")), pin=TEST_PIN)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"pin": TEST_PIN})
        ac.headers["Authorization"] = f"Bearer {resp.json()['token']}"
        sid = "sess-fail"
        await ac.post(
            "/api/v1/chat/message",
            json={"content": "trigger", "context": {}, "session_id": sid},
        )
        hist = await ac.get("/api/v1/chat/history", params={"session_id": sid})
        msgs = hist.json()["messages"]
        assistant = [m for m in msgs if m["role"] == "assistant"][0]
        assert assistant["ok"] is False
        assert assistant["failure_type"] == "engine_error"


@pytest.mark.asyncio
async def test_history_without_session_is_empty(engine_client: AsyncClient):
    # No session_id and a fake engine without a conversation attribute.
    resp = await engine_client.get("/api/v1/chat/history")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []
