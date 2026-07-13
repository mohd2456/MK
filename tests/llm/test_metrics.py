"""Tests for streaming + local-brain observability metrics."""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from mk.llm.base import LLMProvider
from mk.llm.models import LLMMessage, LLMRequest, LLMResponse, MessageRole, ProviderConfig
from mk.llm.router import LLMRouter, _provider_tier
from mk.metrics import MetricsCollector, metrics


class _FakeStreamProvider(LLMProvider):
    def __init__(self, name: str, chunks) -> None:
        super().__init__(ProviderConfig(name=name, base_url="http://x", default_model="m"))
        self._chunks = chunks

    async def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        return LLMResponse(content="".join(self._chunks), provider_used=self.name)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c

    async def health_check(self) -> bool:  # pragma: no cover
        return True


def _req() -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role=MessageRole.USER, content="hi")])


def test_provider_tier_local_vs_cloud():
    assert _provider_tier("local") == "local"
    assert _provider_tier("ollama") == "local"
    assert _provider_tier("openai") == "cloud"
    assert _provider_tier("anthropic") == "cloud"


def test_metrics_collector_counter_and_render():
    c = MetricsCollector()
    c.increment("mk_test_total", labels={"a": "1"})
    c.increment("mk_test_total", labels={"a": "1"})
    assert c.get_counter("mk_test_total", labels={"a": "1"}) == 2.0
    out = c.render_prometheus()
    assert 'mk_test_total{a="1"} 2.0' in out


@pytest.mark.asyncio
async def test_router_stream_records_metrics():
    # Snapshot counters (global singleton) and assert deltas.
    before_chunks = metrics.get_counter("mk_llm_stream_chunks_total", labels={"provider": "local"})
    before_streams = metrics.get_counter(
        "mk_llm_streams_total", labels={"provider": "local", "tier": "local"}
    )
    before_reqs = metrics.get_counter(
        "mk_llm_requests_total", labels={"provider": "local", "tier": "local"}
    )

    router = LLMRouter()
    router.register_provider(_FakeStreamProvider("local", ["a", "b", "c"]))
    chunks = [c async for c in router.stream(_req())]
    assert chunks == ["a", "b", "c"]

    assert (
        metrics.get_counter("mk_llm_stream_chunks_total", labels={"provider": "local"})
        == before_chunks + 3
    )
    assert (
        metrics.get_counter("mk_llm_streams_total", labels={"provider": "local", "tier": "local"})
        == before_streams + 1
    )
    # Successful stream also counts as a request, labelled local.
    assert (
        metrics.get_counter("mk_llm_requests_total", labels={"provider": "local", "tier": "local"})
        == before_reqs + 1
    )


@pytest.mark.asyncio
async def test_router_complete_counts_cloud_request():
    before = metrics.get_counter(
        "mk_llm_requests_total", labels={"provider": "openai", "tier": "cloud"}
    )
    router = LLMRouter()

    class _P(_FakeStreamProvider):
        async def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(content="ok", provider_used=self.name, tokens_used=5)

    router.register_provider(_P("openai", ["ok"]))
    await router.complete(_req())
    assert (
        metrics.get_counter("mk_llm_requests_total", labels={"provider": "openai", "tier": "cloud"})
        == before + 1
    )
