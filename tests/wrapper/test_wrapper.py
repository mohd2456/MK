"""Unit tests for MKWrapper — validation, timeout, failures, fallbacks."""

from __future__ import annotations

import pytest

from mk.llm.base import ProviderError
from mk.llm.base import TimeoutError as ProviderTimeout
from mk.wrapper import ChatRequest, InputValidationError, MKWrapper
from mk.wrapper.errors import AIFailureType

from .conftest import FakeEngine, FakeResponse

pytestmark = pytest.mark.asyncio


async def test_chat_success_returns_ok_result(fake_engine):
    wrapper = MKWrapper(engine=fake_engine)
    result = await wrapper.chat(ChatRequest(content="status", context={"page": "/dashboard"}))
    assert result.ok is True
    assert result.content == "All good."
    assert result.message == "All good."
    assert result.provider == "openai"
    assert result.tokens_used == 7
    assert result.failure is None
    assert len(result.suggestions) > 0
    assert fake_engine.calls == ["status"]


async def test_chat_accepts_dict_payload(fake_engine):
    wrapper = MKWrapper(engine=fake_engine)
    result = await wrapper.chat({"content": "hi", "context": {"page": "/network"}})
    assert result.ok is True
    # Suggestions should reflect the network page.
    assert any(a.category == "network" for a in result.suggestions)


async def test_chat_empty_content_raises_input_validation(fake_engine):
    wrapper = MKWrapper(engine=fake_engine)
    with pytest.raises(InputValidationError) as exc:
        await wrapper.chat({"content": "   "})
    assert "content" in str(exc.value).lower()


async def test_chat_missing_content_raises_input_validation(fake_engine):
    wrapper = MKWrapper(engine=fake_engine)
    with pytest.raises(InputValidationError):
        await wrapper.chat({})


async def test_chat_no_engine_returns_no_engine_failure():
    wrapper = MKWrapper()  # no engine, no factory
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.NO_ENGINE.value
    assert result.degraded is True
    # Suggestions still attached even in the degraded path.
    assert len(result.suggestions) > 0


async def test_chat_timeout_returns_timeout_failure():
    wrapper = MKWrapper(engine=FakeEngine(delay=2.0), timeout=1.0)
    result = await wrapper.chat(ChatRequest(content="slow"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.TIMEOUT.value
    assert result.failure.retryable is True


async def test_chat_engine_exception_returns_engine_error():
    wrapper = MKWrapper(engine=FakeEngine(exc=RuntimeError("boom")))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.ENGINE_ERROR.value
    assert "boom" in result.failure.detail


async def test_chat_provider_error_maps_to_provider_unavailable():
    wrapper = MKWrapper(engine=FakeEngine(exc=ProviderError("down", provider="openai")))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.PROVIDER_UNAVAILABLE.value


async def test_chat_provider_timeout_maps_to_timeout():
    wrapper = MKWrapper(engine=FakeEngine(exc=ProviderTimeout("openai", 30.0)))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.TIMEOUT.value


async def test_chat_empty_output_detected():
    wrapper = MKWrapper(engine=FakeEngine(reply="   "))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.EMPTY_OUTPUT.value


async def test_chat_degenerate_output_detected():
    wrapper = MKWrapper(engine=FakeEngine(reply="loop " * 60))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.MALFORMED_OUTPUT.value


async def test_chat_schema_invalid_when_json_expected():
    wrapper = MKWrapper(engine=FakeEngine(reply="not json here"))
    result = await wrapper.chat(ChatRequest(content="give me json", expect_json=True))
    assert result.ok is False
    assert result.failure_type == AIFailureType.SCHEMA_INVALID.value


async def test_chat_valid_json_when_expected_is_ok():
    wrapper = MKWrapper(engine=FakeEngine(reply='{"status": "ok"}'))
    result = await wrapper.chat(ChatRequest(content="give me json", expect_json=True))
    assert result.ok is True


async def test_degraded_flag_set_when_no_provider_and_not_direct():
    # No provider used and not a direct command => degraded (no-LLM mode).
    engine = FakeEngine(reply="help text", provider_used=None, was_direct_command=False)
    wrapper = MKWrapper(engine=engine)
    result = await wrapper.chat(ChatRequest(content="help"))
    assert result.ok is True
    assert result.degraded is True


async def test_direct_command_not_marked_degraded():
    engine = FakeEngine(reply="pool list", provider_used=None, was_direct_command=True)
    wrapper = MKWrapper(engine=engine)
    result = await wrapper.chat(ChatRequest(content="storage"))
    assert result.ok is True
    assert result.degraded is False
    assert result.was_direct_command is True


async def test_string_response_supported():
    # An engine that returns a bare string still works.
    wrapper = MKWrapper(engine=FakeEngine(response="just a string"))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is True
    assert result.content == "just a string"


async def test_lazy_sync_engine_factory():
    built = {}

    def factory():
        built["yes"] = True
        return FakeEngine(reply="lazy hello")

    wrapper = MKWrapper(engine_factory=factory)
    assert wrapper.has_engine is True
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is True
    assert result.content == "lazy hello"
    assert built == {"yes": True}


async def test_lazy_async_engine_factory():
    async def factory():
        return FakeEngine(reply="async lazy")

    wrapper = MKWrapper(engine_factory=factory)
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is True
    assert result.content == "async lazy"


async def test_factory_failure_degrades_to_no_engine():
    def bad_factory():
        raise RuntimeError("cannot build")

    wrapper = MKWrapper(engine_factory=bad_factory)
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.NO_ENGINE.value


async def test_get_suggestions_accepts_dict_and_none():
    wrapper = MKWrapper()
    assert len(wrapper.get_suggestions({"page": "/dashboard"})) > 0
    assert len(wrapper.get_suggestions(None)) > 0


async def test_response_missing_final_response_treated_as_empty():
    # An object with final_response=None => empty output failure.
    resp = FakeResponse(final_response=None)  # type: ignore[arg-type]
    wrapper = MKWrapper(engine=FakeEngine(response=resp))
    result = await wrapper.chat(ChatRequest(content="hi"))
    assert result.ok is False
    assert result.failure_type == AIFailureType.EMPTY_OUTPUT.value
