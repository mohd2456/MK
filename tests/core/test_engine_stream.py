"""Tests for MKEngine.stream_reply (real engine streaming path)."""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from mk.core.engine import MKEngine
from mk.llm.models import LLMRequest


class FakeRouter:
    """Minimal stand-in for LLMRouter exposing an async stream()."""

    def __init__(self, chunks) -> None:
        self._chunks = chunks

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_reply_no_llm_degrades_single_chunk():
    """With no LLM and no tools, stream_reply yields the offline handler text."""
    engine = MKEngine()
    chunks = [c async for c in engine.stream_reply("tell me a story about dragons")]
    assert len(chunks) == 1
    assert chunks[0]  # non-empty offline message
    # The reply was recorded to the conversation.
    assert engine.conversation.messages[-1].content == chunks[0]


@pytest.mark.asyncio
async def test_stream_reply_streams_from_router():
    """When an LLM router is configured, tokens are streamed through it."""
    engine = MKEngine()
    engine._llm_router = FakeRouter(["Once ", "upon ", "a ", "time"])
    chunks = [c async for c in engine.stream_reply("tell me a story")]
    assert "".join(chunks) == "Once upon a time"
    # Full reply recorded to conversation history.
    assert engine.conversation.messages[-1].content == "Once upon a time"


@pytest.mark.asyncio
async def test_stream_reply_records_user_message():
    engine = MKEngine()
    _ = [c async for c in engine.stream_reply("hello there")]
    # First message recorded is the user's input.
    assert engine.conversation.messages[0].content == "hello there"
