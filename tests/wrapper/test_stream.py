"""Tests for MKWrapper.stream_chat streaming behavior."""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from mk.wrapper import InputValidationError, MKWrapper


class StreamingEngine:
    """Fake engine exposing an async stream_reply generator."""

    def __init__(self, chunks, exc: Exception | None = None) -> None:
        self._chunks = chunks
        self._exc = exc

    async def stream_reply(self, content: str) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c
        if self._exc is not None:
            raise self._exc


class NonStreamingEngine:
    """Fake engine with only process() (no stream_reply) — forces fallback."""

    async def process(self, content: str):
        class R:
            final_response = "full reply"
            provider_used = "openai"
            was_direct_command = False
            tokens_used = 3
            cost = 0.0

        return R()


@pytest.mark.asyncio
async def test_stream_chat_yields_chunks():
    wrapper = MKWrapper(engine=StreamingEngine(["Hel", "lo"]))
    out = [c async for c in wrapper.stream_chat({"content": "hi"})]
    assert "".join(out) == "Hello"


@pytest.mark.asyncio
async def test_stream_chat_no_engine_degrades_to_single_message():
    wrapper = MKWrapper(engine=None)
    out = [c async for c in wrapper.stream_chat({"content": "hi"})]
    assert len(out) == 1
    assert out[0]  # a non-empty calm message


@pytest.mark.asyncio
async def test_stream_chat_falls_back_when_no_stream_reply():
    wrapper = MKWrapper(engine=NonStreamingEngine())
    out = [c async for c in wrapper.stream_chat({"content": "hi"})]
    assert "".join(out) == "full reply"


@pytest.mark.asyncio
async def test_stream_chat_invalid_input_raises():
    wrapper = MKWrapper(engine=StreamingEngine(["x"]))
    with pytest.raises(InputValidationError):
        async for _ in wrapper.stream_chat({"content": "   "}):
            pass


@pytest.mark.asyncio
async def test_stream_chat_isolates_mid_stream_error():
    """An error after some chunks is caught and turned into a trailing notice."""
    wrapper = MKWrapper(engine=StreamingEngine(["partial"], exc=RuntimeError("boom")))
    out = [c async for c in wrapper.stream_chat({"content": "hi"})]
    assert out[0] == "partial"
    # A trailing fallback chunk is appended rather than the error propagating.
    assert len(out) >= 2
