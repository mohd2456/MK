"""Tests for the optional Headroom-backed context compression layer.

A fake ``headroom`` module is injected via ``sys.modules`` so these tests never
require the real optional dependency.
"""

from __future__ import annotations

import json
import sys
import types
from typing import AsyncIterator

import pytest

from mk.llm.base import LLMProvider
from mk.llm.compression import ContextCompressor
from mk.llm.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ProviderConfig,
)
from mk.llm.router import LLMRouter


def _messages() -> list[LLMMessage]:
    return [
        LLMMessage(role=MessageRole.SYSTEM, content="You are MK."),
        LLMMessage(role=MessageRole.USER, content="which containers use most memory?"),
        LLMMessage(
            role=MessageRole.TOOL,
            content=json.dumps({"containers": [{"n": i, "mem": i * 10} for i in range(30)]}),
        ),
    ]


def _install_fake_headroom(monkeypatch, *, raises: bool = False):
    """Inject a fake ``headroom`` module and return it."""
    fake = types.ModuleType("headroom")

    class FakeResult:
        def __init__(self, messages):
            self.messages = messages
            self.tokens_before = 1000
            self.tokens_after = 400
            self.tokens_saved = 600
            self.compression_ratio = 0.4
            self.transforms_applied = ["SmartCrusher"]

    def fake_compress(messages, model=None, **kwargs):
        if raises:
            raise RuntimeError("kaboom")
        out = []
        for m in messages:
            content = m["content"]
            out.append(
                {
                    "role": m["role"],
                    "content": content[:16] + "..." if len(content) > 40 else content,
                }
            )
        return FakeResult(out)

    fake.compress = fake_compress
    monkeypatch.setitem(sys.modules, "headroom", fake)
    return fake


# ── ContextCompressor unit tests ────────────────────────────────────────


def test_disabled_is_noop():
    c = ContextCompressor(enabled=False)
    msgs = _messages()
    out, stats = c.compress_messages(msgs)
    assert out is msgs
    assert stats.applied is False


def test_enabled_but_unavailable_is_noop(monkeypatch):
    # Ensure headroom import fails.
    monkeypatch.setitem(sys.modules, "headroom", None)
    c = ContextCompressor(enabled=True)
    msgs = _messages()
    out, stats = c.compress_messages(msgs)
    assert stats.applied is False
    assert stats.available is False
    assert out == msgs


def test_applied_with_fake_headroom(monkeypatch):
    _install_fake_headroom(monkeypatch)
    c = ContextCompressor(enabled=True)
    msgs = _messages()
    out, stats = c.compress_messages(msgs)
    assert stats.applied is True
    assert stats.available is True
    assert stats.tokens_saved == 600
    assert stats.compression_ratio == 0.4
    assert stats.transforms_applied == ["SmartCrusher"]
    # Roles/order preserved, content changed on the big tool message.
    assert [m.role for m in out] == [m.role for m in msgs]
    assert out[2].content != msgs[2].content


def test_exception_returns_original(monkeypatch):
    _install_fake_headroom(monkeypatch, raises=True)
    c = ContextCompressor(enabled=True)
    msgs = _messages()
    out, stats = c.compress_messages(msgs)
    assert stats.applied is False
    assert stats.error is not None
    assert out is msgs


def test_shape_mismatch_skips(monkeypatch):
    fake = types.ModuleType("headroom")

    class R:
        messages = [{"role": "system", "content": "only one"}]  # fewer than input
        tokens_before = 10
        tokens_after = 5
        tokens_saved = 5
        compression_ratio = 0.5
        transforms_applied: list = []

    fake.compress = lambda messages, **kw: R()
    monkeypatch.setitem(sys.modules, "headroom", fake)

    c = ContextCompressor(enabled=True)
    msgs = _messages()
    out, stats = c.compress_messages(msgs)
    assert stats.applied is False
    assert out is msgs  # original preserved on mismatch


def test_empty_messages_noop():
    c = ContextCompressor(enabled=True)
    out, stats = c.compress_messages([])
    assert out == []
    assert stats.applied is False


def test_from_env_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MK_COMPRESSION", raising=False)
    assert ContextCompressor.from_env().enabled is False


def test_from_env_enable(monkeypatch):
    monkeypatch.setenv("MK_COMPRESSION", "1")
    monkeypatch.setenv("MK_COMPRESSION_MODEL", "gpt-4o")
    c = ContextCompressor.from_env()
    assert c.enabled is True
    assert c._model == "gpt-4o"


# ── Router integration ──────────────────────────────────────────────────


class _CapturingProvider(LLMProvider):
    """Provider that records the messages it was asked to complete."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.seen_contents: list[str] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.seen_contents = [m.content for m in request.messages]
        return LLMResponse(content="ok", provider_used=self.name, model_used="m")

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:  # pragma: no cover
        yield "ok"

    async def health_check(self) -> bool:  # pragma: no cover
        return True


def _config() -> ProviderConfig:
    return ProviderConfig(name="p", api_key="k", base_url="http://x", default_model="m")


@pytest.mark.asyncio
async def test_router_applies_compression_when_active(monkeypatch):
    _install_fake_headroom(monkeypatch)
    router = LLMRouter(compressor=ContextCompressor(enabled=True))
    provider = _CapturingProvider(_config())
    router.register_provider(provider)

    resp = await router.complete(LLMRequest(messages=_messages()))
    assert resp.content == "ok"
    # The big tool message content should have been compressed before dispatch.
    original = _messages()[2].content
    assert provider.seen_contents[2] != original


@pytest.mark.asyncio
async def test_router_no_compression_when_disabled(monkeypatch):
    _install_fake_headroom(monkeypatch)
    router = LLMRouter(compressor=ContextCompressor(enabled=False))
    provider = _CapturingProvider(_config())
    router.register_provider(provider)

    original = _messages()
    await router.complete(LLMRequest(messages=original))
    assert provider.seen_contents == [m.content for m in original]
