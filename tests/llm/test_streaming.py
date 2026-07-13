"""Tests for LLM streaming: router.stream fallback + provider integration."""

from __future__ import annotations

from typing import AsyncIterator, List

import pytest

from mk.llm.base import LLMProvider, ProviderError
from mk.llm.models import LLMMessage, LLMRequest, LLMResponse, MessageRole, ProviderConfig
from mk.llm.router import LLMRouter


def _cfg(name: str) -> ProviderConfig:
    return ProviderConfig(name=name, base_url="http://x", default_model="m")


class FakeStreamProvider(LLMProvider):
    """A provider whose stream() yields preset chunks or fails."""

    def __init__(self, name: str, chunks: List[str], fail: bool = False) -> None:
        super().__init__(_cfg(name))
        self._chunks = chunks
        self._fail = fail

    async def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        return LLMResponse(content="".join(self._chunks), provider_used=self.name)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        if self._fail:
            raise ProviderError("boom", provider=self.name, retryable=True)
        for c in self._chunks:
            yield c

    async def health_check(self) -> bool:  # pragma: no cover
        return True


def _req() -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role=MessageRole.USER, content="hi")])


@pytest.mark.asyncio
async def test_router_stream_yields_chunks():
    router = LLMRouter()
    router.register_provider(FakeStreamProvider("openai", ["Hel", "lo", "!"]))
    out = [c async for c in router.stream(_req())]
    assert "".join(out) == "Hello!"


@pytest.mark.asyncio
async def test_router_stream_falls_back_before_first_chunk():
    """A provider that fails before emitting output falls back to the next."""
    router = LLMRouter()
    # cheaper provider (cost 0) is tried first; make it fail, second succeeds.
    failing = FakeStreamProvider("groq", [], fail=True)
    working = FakeStreamProvider("openai", ["ok"])
    router.register_provider(failing)
    router.register_provider(working)
    out = [c async for c in router.stream(_req())]
    assert "".join(out) == "ok"


@pytest.mark.asyncio
async def test_router_stream_no_providers_raises():
    router = LLMRouter()
    with pytest.raises(ProviderError):
        async for _ in router.stream(_req()):
            pass


@pytest.mark.asyncio
async def test_router_stream_all_fail_raises():
    router = LLMRouter()
    router.register_provider(FakeStreamProvider("groq", [], fail=True))
    router.register_provider(FakeStreamProvider("openai", [], fail=True))
    with pytest.raises(ProviderError):
        async for _ in router.stream(_req()):
            pass
