"""Tests for the MKWrapper orchestration behavior."""

from __future__ import annotations

import asyncio

import pytest

from mk.llm.base import ProviderError
from mk.wrapper import ChatRequest, InputValidationError, MKWrapper, PageContext
from mk.wrapper.errors import AIFailureType


@pytest.mark.asyncio
class TestChatSuccess:
    async def test_successful_reply(self, fake_engine):
        wrapper = MKWrapper(engine=fake_engine)
        result = await wrapper.chat("What's my pool status?")
        assert result.ok is True
        assert result.failure is None
        assert result.content == "Hello from the engine."
        assert result.tokens_used == 12
        assert result.provider_used == "fake-provider"
        assert fake_engine.calls == ["What's my pool status?"]

    async def test_actions_reflect_context(self, fake_engine):
        wrapper = MKWrapper(engine=fake_engine)
        result = await wrapper.chat(ChatRequest(content="hi", context=PageContext(path="/network")))
        labels = [a.label for a in result.actions]
        assert "WireGuard peers" in labels

    async def test_llm_available_reflected(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(has_llm=True))
        result = await wrapper.chat("hi")
        assert result.llm_available is True
        assert result.degraded is False

    async def test_no_llm_is_degraded_not_failed(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(has_llm=False, reply="command output"))
        result = await wrapper.chat("status")
        assert result.ok is True
        assert result.degraded is True
        assert result.llm_available is False


@pytest.mark.asyncio
class TestInputValidation:
    async def test_empty_content_raises(self, fake_engine):
        wrapper = MKWrapper(engine=fake_engine)
        with pytest.raises(InputValidationError):
            await wrapper.chat("   ")

    async def test_dict_request_validated(self, fake_engine):
        wrapper = MKWrapper(engine=fake_engine)
        result = await wrapper.chat({"content": "hello", "context": {"path": "/storage"}})
        assert result.ok is True

    async def test_invalid_dict_raises(self, fake_engine):
        wrapper = MKWrapper(engine=fake_engine)
        with pytest.raises(InputValidationError):
            await wrapper.chat({"content": ""})


@pytest.mark.asyncio
class TestFailureHandling:
    async def test_timeout_returns_failure(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(delay=5.0), timeout=1.0)
        result = await wrapper.chat("slow request")
        assert result.ok is False
        assert result.failure.type == AIFailureType.TIMEOUT
        assert result.failure.retryable is True
        # A safe, user-facing message is still returned.
        assert result.content
        # Suggestions are still attached even on failure.
        assert result.actions

    async def test_engine_exception_returns_failure(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(raise_exc=RuntimeError("boom")))
        result = await wrapper.chat("trigger error")
        assert result.ok is False
        assert result.failure.type == AIFailureType.ENGINE_ERROR
        assert "boom" in (result.failure.detail or "")

    async def test_provider_error_classified(self, make_engine):
        exc = ProviderError("all down", provider="router", retryable=True)
        wrapper = MKWrapper(engine=make_engine(raise_exc=exc))
        result = await wrapper.chat("hi")
        assert result.ok is False
        assert result.failure.type == AIFailureType.PROVIDER_UNAVAILABLE

    async def test_empty_output_detected(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(reply=""))
        result = await wrapper.chat("hi")
        assert result.ok is False
        assert result.failure.type == AIFailureType.EMPTY_OUTPUT

    async def test_malformed_output_detected(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(reply="loop " * 200))
        result = await wrapper.chat("hi")
        assert result.ok is False
        assert result.failure.type == AIFailureType.MALFORMED_OUTPUT

    async def test_schema_invalid_detected(self, make_engine):
        wrapper = MKWrapper(engine=make_engine(reply="not json"))
        result = await wrapper.chat(ChatRequest(content="hi", expects_json=True))
        assert result.ok is False
        assert result.failure.type == AIFailureType.SCHEMA_INVALID


@pytest.mark.asyncio
class TestEngineConstruction:
    async def test_no_engine_returns_graceful_failure(self):
        wrapper = MKWrapper(engine=None, engine_factory=lambda: None)
        result = await wrapper.chat("hi")
        assert result.ok is False
        assert result.failure.type == AIFailureType.NO_ENGINE
        assert result.content

    async def test_engine_factory_exception_is_safe(self):
        def broken_factory():
            raise RuntimeError("cannot build")

        wrapper = MKWrapper(engine=None, engine_factory=broken_factory)
        result = await wrapper.chat("hi")
        assert result.ok is False
        assert result.failure.type == AIFailureType.NO_ENGINE

    async def test_lazy_build_happens_once(self, make_engine):
        calls = {"count": 0}

        def factory():
            calls["count"] += 1
            return make_engine()

        wrapper = MKWrapper(engine=None, engine_factory=factory)
        await wrapper.chat("hi")
        await wrapper.chat("again")
        assert calls["count"] == 1

    async def test_async_factory_supported(self, make_engine):
        async def factory():
            await asyncio.sleep(0)
            return make_engine()

        wrapper = MKWrapper(engine=None, engine_factory=factory)
        result = await wrapper.chat("hi")
        assert result.ok is True


class TestSuggestionsApi:
    def test_suggestions_accepts_string(self):
        wrapper = MKWrapper(engine=None, engine_factory=lambda: None)
        actions = wrapper.suggestions("/apps")
        assert any(a.label == "Restart Plex" for a in actions)

    def test_context_label(self):
        wrapper = MKWrapper(engine=None, engine_factory=lambda: None)
        assert wrapper.context_label("/system") == "System"
