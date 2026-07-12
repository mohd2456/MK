"""WebSocket chat robustness tests.

Uses Starlette's sync TestClient (the standard tool for exercising WebSocket
routes) to confirm the socket survives bad input and stays usable.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mk.web.app import create_app

TEST_PIN = "1234"


def _client_and_token() -> tuple[TestClient, str]:
    app = create_app(pin=TEST_PIN)
    client = TestClient(app)
    resp = client.post("/api/v1/auth/login", json={"pin": TEST_PIN})
    assert resp.status_code == 200
    return client, resp.json()["token"]


def test_ws_rejects_invalid_token():
    app = create_app(pin=TEST_PIN)
    client = TestClient(app)
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat?token=bogus") as ws:
            ws.receive_text()


def test_ws_malformed_json_does_not_kill_connection():
    client, token = _client_and_token()
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        # A garbage frame must not tear down the socket.
        ws.send_text("this is not json {{{")
        err = ws.receive_json()
        assert err["type"] == "error"

        # Connection is still alive: ping should still get a pong.
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"


def test_ws_non_object_json_is_rejected_gracefully():
    client, token = _client_and_token()
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        ws.send_text("[1, 2, 3]")  # valid JSON, but not an object
        err = ws.receive_json()
        assert err["type"] == "error"
        # Still usable.
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_ws_chat_message_roundtrip_no_engine():
    """A chat message with no engine returns a graceful failure envelope."""
    client, token = _client_and_token()
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        ws.send_json({"type": "chat_message", "id": "m1", "content": "hi", "context": {}})
        # First frame: typing on.
        first = ws.receive_json()
        assert first == {"type": "typing_indicator", "active": True}
        # Then typing off.
        assert ws.receive_json() == {"type": "typing_indicator", "active": False}
        # Then the response envelope.
        resp = ws.receive_json()
        assert resp["type"] == "chat_response"
        assert resp["done"] is True
        assert resp["ok"] is False
        assert resp["failure_type"] == "no_engine"
        assert "retryable" in resp
