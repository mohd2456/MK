"""Tests for the SSE chat streaming endpoint."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient


def _parse_sse(text: str):
    """Parse SSE 'data: {json}' lines into a list of event dicts."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_chat_stream_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/chat/stream", json={"content": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_degraded_no_engine(auth_client: AsyncClient):
    """With no engine configured, the stream still emits a message + done."""
    resp = await auth_client.post("/api/v1/chat/stream", json={"content": "how are you?"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert events, "expected at least one SSE event"
    # Final event is a 'done'.
    assert events[-1]["type"] == "done"
    assert events[-1]["ok"] is True
    # At least one token event carrying the degraded message.
    tokens = [e for e in events if e["type"] == "token"]
    assert tokens
    assert any(e["content"] for e in tokens)


@pytest.mark.asyncio
async def test_chat_stream_rejects_empty_content(auth_client: AsyncClient):
    resp = await auth_client.post("/api/v1/chat/stream", json={"content": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_no_engine_reply_is_not_captured(tmp_path):
    """Degraded no-engine replies must NOT be captured as training data."""
    from httpx import ASGITransport, AsyncClient as AC

    from mk.web.app import create_app

    capture_file = tmp_path / "captured.jsonl"
    app = create_app(
        pin="1234",
        audit_log_dir=str(tmp_path / "audit"),
        capture_conversations=True,
        capture_path=str(capture_file),
    )
    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://t") as c:
        tok = (await c.post("/api/v1/auth/login", json={"pin": "1234"})).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        # Non-streaming chat with no engine -> degraded -> must not be captured.
        await c.post("/api/v1/chat/message", json={"content": "hello there"})

    from mk.web import app as web_app

    store = getattr(web_app, "_chat_history", None)
    if store is not None:
        await store.close()

    # Nothing captured because the reply was degraded (no engine).
    if capture_file.exists():
        assert capture_file.read_text().strip() == ""


@pytest.mark.asyncio
async def test_engine_reply_is_captured_via_stream(tmp_path):
    """With an engine present, a streamed reply is captured for retraining."""
    from httpx import ASGITransport, AsyncClient as AC

    from mk.web.app import create_app

    class _Engine:
        async def stream_reply(self, content):
            for c in ["Restarting ", "Plex."]:
                yield c

    capture_file = tmp_path / "captured.jsonl"
    app = create_app(
        pin="1234",
        mk_engine=_Engine(),
        audit_log_dir=str(tmp_path / "audit"),
        capture_conversations=True,
        capture_path=str(capture_file),
    )
    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://t") as c:
        tok = (await c.post("/api/v1/auth/login", json={"pin": "1234"})).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        resp = await c.post("/api/v1/chat/stream", json={"content": "restart plex"})
        assert resp.status_code == 200
        _ = resp.text  # drain the stream

    from mk.web import app as web_app

    store = getattr(web_app, "_chat_history", None)
    if store is not None:
        await store.close()

    import json as _json

    assert capture_file.exists()
    line = capture_file.read_text().strip()
    record = _json.loads(line)
    contents = {m["role"]: m["content"] for m in record["messages"]}
    assert contents["user"] == "restart plex"
    assert contents["assistant"] == "Restarting Plex."
