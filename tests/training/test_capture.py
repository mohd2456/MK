"""Tests for conversation capture + retraining ingest."""

from __future__ import annotations

import json

from mk.training import ConversationCapture, ingest, load_jsonl


def test_capture_disabled_by_default_writes_nothing(tmp_path):
    cap = ConversationCapture(path=str(tmp_path / "c.jsonl"), enabled=False)
    assert cap.enabled is False
    assert cap.capture("hi", "hello") is False
    assert cap.count() == 0
    assert not (tmp_path / "c.jsonl").exists()


def test_capture_writes_training_format(tmp_path):
    out = tmp_path / "c.jsonl"
    cap = ConversationCapture(path=str(out), enabled=True)
    assert cap.capture("restart plex", "Done, plex restarted.") is True
    assert cap.count() == 1

    line = out.read_text().strip()
    record = json.loads(line)
    roles = [m["role"] for m in record["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert record["messages"][1]["content"] == "restart plex"
    assert record["messages"][2]["content"] == "Done, plex restarted."


def test_capture_skips_empty_and_failed(tmp_path):
    cap = ConversationCapture(path=str(tmp_path / "c.jsonl"), enabled=True)
    assert cap.capture("", "reply") is False       # empty user
    assert cap.capture("prompt", "   ") is False    # empty assistant
    assert cap.capture("prompt", "reply", ok=False) is False  # failed reply
    assert cap.count() == 0


def test_capture_enabled_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MK_CAPTURE_CONVERSATIONS", "1")
    cap = ConversationCapture(path=str(tmp_path / "c.jsonl"))
    assert cap.enabled is True


def test_ingest_dedupes_and_appends(tmp_path):
    captured = tmp_path / "captured.jsonl"
    train = tmp_path / "mk_train.jsonl"

    def line(u, a, sys="s"):
        return json.dumps(
            {
                "messages": [
                    {"role": "system", "content": sys},
                    {"role": "user", "content": u},
                    {"role": "assistant", "content": a},
                ]
            }
        )

    # Existing training example.
    train.write_text(line("existing q", "existing a") + "\n")
    # Captured: one new, one duplicate of existing, one invalid.
    captured.write_text(
        "\n".join(
            [
                line("new q", "new a"),
                line("existing q", "existing a"),  # duplicate (ignores system)
                json.dumps({"messages": [{"role": "user", "content": "no assistant"}]}),
            ]
        )
        + "\n"
    )

    stats = ingest(captured_path=captured, train_path=train)
    assert stats["captured"] == 3
    assert stats["added"] == 1
    assert stats["duplicates"] == 1
    assert stats["invalid"] == 1

    rows = load_jsonl(train)
    assert len(rows) == 2  # original + 1 new
    users = [m["content"] for r in rows for m in r["messages"] if m["role"] == "user"]
    assert "new q" in users


def test_ingest_normalizes_system_prompt(tmp_path):
    captured = tmp_path / "captured.jsonl"
    train = tmp_path / "mk_train.jsonl"
    captured.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "old prompt"},
                    {"role": "user", "content": "q"},
                    {"role": "assistant", "content": "a"},
                ]
            }
        )
        + "\n"
    )
    ingest(captured_path=captured, train_path=train, normalize_system="CANON")
    rows = load_jsonl(train)
    assert rows[0]["messages"][0] == {"role": "system", "content": "CANON"}
