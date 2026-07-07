"""Tests for the UniversalProvider and provider factory.

Verifies that:
- UniversalProvider works with different endpoint paths
- Provider factory creates correct provider types from KeyManager
- configure_router_from_keys builds a working router
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mk.llm.base import AuthenticationError, ProviderError, RateLimitError
from mk.llm.keys import KeyManager, PROVIDER_ENDPOINTS, PROVIDER_MODELS
from mk.llm.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ProviderConfig,
)
from mk.llm.provider_factory import (
    CUSTOM_PROVIDERS,
    UNIVERSAL_PROVIDERS,
    _build_config,
    configure_router_from_keys,
    create_provider,
    create_providers_from_keys,
)
from mk.llm.providers.anthropic_provider import AnthropicProvider
from mk.llm.providers.gemini_provider import GeminiProvider
from mk.llm.providers.openai_provider import OpenAIProvider
from mk.llm.providers.universal_provider import UniversalProvider


def make_request(content: str = "Hello") -> LLMRequest:
    """Create a simple test request."""
    return LLMRequest(
        messages=[LLMMessage(role=MessageRole.USER, content=content)],
        max_tokens=100,
        temperature=0.7,
    )


def make_config(name: str, base_url: str = "http://test.local") -> ProviderConfig:
    """Create a test provider config."""
    return ProviderConfig(
        name=name,
        api_key="test-key-123",
        base_url=base_url,
        models=["test-model"],
        default_model="test-model",
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.002,
        timeout_seconds=5.0,
        max_retries=1,
    )


def mock_openai_response(content: str = "Hello from provider!") -> Dict[str, Any]:
    """Standard OpenAI-compatible response."""
    return {
        "choices": [{
            "message": {
                "content": content,
                "tool_calls": [],
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


# --- UniversalProvider Tests ---


class TestUniversalProvider:
    """Tests for the UniversalProvider."""

    async def test_complete_with_default_path(self) -> None:
        """Test completion using default /v1/chat/completions path."""
        config = make_config("together", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_openai_response("Together response"))
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local",
            transport=transport,
            headers={"Authorization": "Bearer test"},
        )

        response = await provider.complete(make_request())
        assert response.content == "Together response"
        assert response.provider_used == "together"
        assert response.tokens_used == 15

    async def test_complete_with_groq_path(self) -> None:
        """Test completion using Groq's /openai/v1/chat/completions path."""
        config = make_config("groq", "http://test.local")
        provider = UniversalProvider(config)

        # Verify the path was set correctly from the CHAT_COMPLETIONS_PATHS mapping
        assert provider._chat_path == "/openai/v1/chat/completions"

        called_paths = []

        def handler(req: httpx.Request) -> httpx.Response:
            called_paths.append(req.url.path)
            return httpx.Response(200, json=mock_openai_response("Groq fast"))

        transport = httpx.MockTransport(handler)
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Groq fast"
        assert called_paths == ["/openai/v1/chat/completions"]

    async def test_complete_with_perplexity_path(self) -> None:
        """Test completion using Perplexity's /chat/completions path."""
        config = make_config("perplexity", "http://test.local")
        provider = UniversalProvider(config)

        assert provider._chat_path == "/chat/completions"

        called_paths = []

        def handler(req: httpx.Request) -> httpx.Response:
            called_paths.append(req.url.path)
            return httpx.Response(200, json=mock_openai_response("Search result"))

        transport = httpx.MockTransport(handler)
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Search result"
        assert called_paths == ["/chat/completions"]

    async def test_complete_with_custom_path(self) -> None:
        """Test completion with an explicit custom path override."""
        config = make_config("custom-provider", "http://test.local")
        provider = UniversalProvider(config, chat_path="/api/generate")

        assert provider._chat_path == "/api/generate"

        called_paths = []

        def handler(req: httpx.Request) -> httpx.Response:
            called_paths.append(req.url.path)
            return httpx.Response(200, json=mock_openai_response("Custom"))

        transport = httpx.MockTransport(handler)
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Custom"
        assert called_paths == ["/api/generate"]

    async def test_complete_with_tool_calls(self) -> None:
        """Test that tool calls are parsed correctly."""
        config = make_config("fireworks", "http://test.local")
        provider = UniversalProvider(config)

        mock_data = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_abc",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "test"}',
                        },
                    }],
                },
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_data)
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
        assert response.tool_calls[0].arguments == {"query": "test"}

    async def test_complete_auth_error(self) -> None:
        """Test authentication error."""
        config = make_config("deepseek", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, json={"error": "invalid key"})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(AuthenticationError):
            await provider.complete(make_request())

    async def test_complete_rate_limit(self) -> None:
        """Test rate limit handling."""
        config = make_config("openrouter", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"retry-after": "1"})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(RateLimitError):
            await provider.complete(make_request())

    async def test_complete_server_error(self) -> None:
        """Test server error handling."""
        config = make_config("cohere", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="Internal Server Error")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(make_request())
        assert exc_info.value.status_code == 500
        assert "cohere" in str(exc_info.value)

    async def test_health_check_success(self) -> None:
        """Test successful health check."""
        config = make_config("together", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"data": []})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        assert await provider.health_check() is True

    async def test_health_check_failure(self) -> None:
        """Test failed health check."""
        config = make_config("together", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="error")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        assert await provider.health_check() is False

    async def test_health_check_uses_correct_models_path(self) -> None:
        """Test that health check uses the correct models endpoint."""
        config = make_config("groq", "http://test.local")
        provider = UniversalProvider(config)

        called_paths = []

        def handler(req: httpx.Request) -> httpx.Response:
            called_paths.append(req.url.path)
            return httpx.Response(200, json={"data": []})

        transport = httpx.MockTransport(handler)
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        await provider.health_check()
        assert called_paths == ["/openai/v1/models"]

    async def test_provider_name_in_error_messages(self) -> None:
        """Test that error messages include the provider name."""
        config = make_config("mistral", "http://test.local")
        provider = UniversalProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(503, text="Service Unavailable")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(make_request())
        assert "mistral" in str(exc_info.value).lower()

    async def test_inherits_openai_message_formatting(self) -> None:
        """Test that message formatting from OpenAIProvider works."""
        config = make_config("together", "http://test.local")
        provider = UniversalProvider(config)

        # Verify _format_messages is inherited and works
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
            LLMMessage(role=MessageRole.USER, content="Hi"),
        ]
        formatted = provider._format_messages(messages)
        assert formatted[0]["role"] == "system"
        assert formatted[0]["content"] == "You are helpful."
        assert formatted[1]["role"] == "user"


# --- Provider Factory Tests ---


class TestProviderFactory:
    """Tests for the provider factory functions."""

    def test_build_config_openai(self) -> None:
        """Test building config for OpenAI."""
        config = _build_config("openai", "sk-test-key")
        assert config.name == "openai"
        assert config.api_key == "sk-test-key"
        assert config.base_url == PROVIDER_ENDPOINTS["openai"]
        assert "gpt-4o" in config.models
        assert config.default_model == "gpt-4o"
        assert config.cost_per_1k_input > 0

    def test_build_config_groq(self) -> None:
        """Test building config for Groq."""
        config = _build_config("groq", "gsk_test")
        assert config.name == "groq"
        assert config.base_url == "https://api.groq.com/openai/v1"
        assert "llama-3.3-70b-versatile" in config.models

    def test_build_config_unknown_provider(self) -> None:
        """Test building config for an unknown provider."""
        config = _build_config("unknown", "key123")
        assert config.name == "unknown"
        assert config.base_url == ""
        assert config.models == []
        assert config.default_model == ""

    def test_create_provider_anthropic(self) -> None:
        """Test that anthropic gets AnthropicProvider."""
        provider = create_provider("anthropic", "sk-ant-test")
        assert isinstance(provider, AnthropicProvider)
        assert provider.name == "anthropic"

    def test_create_provider_openai(self) -> None:
        """Test that openai gets OpenAIProvider."""
        provider = create_provider("openai", "sk-test")
        assert isinstance(provider, OpenAIProvider)
        # Should NOT be UniversalProvider (it inherits from OpenAI)
        assert type(provider) is OpenAIProvider
        assert provider.name == "openai"

    def test_create_provider_gemini(self) -> None:
        """Test that gemini gets GeminiProvider."""
        provider = create_provider("gemini", "AIza-test")
        assert isinstance(provider, GeminiProvider)
        assert provider.name == "gemini"

    def test_create_provider_groq(self) -> None:
        """Test that groq gets UniversalProvider."""
        provider = create_provider("groq", "gsk_test")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "groq"

    def test_create_provider_together(self) -> None:
        """Test that together gets UniversalProvider."""
        provider = create_provider("together", "abc123")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "together"

    def test_create_provider_fireworks(self) -> None:
        """Test that fireworks gets UniversalProvider."""
        provider = create_provider("fireworks", "fw_test")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "fireworks"

    def test_create_provider_deepseek(self) -> None:
        """Test that deepseek gets UniversalProvider."""
        provider = create_provider("deepseek", "sk-deep-test")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "deepseek"

    def test_create_provider_perplexity(self) -> None:
        """Test that perplexity gets UniversalProvider."""
        provider = create_provider("perplexity", "pplx-test")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "perplexity"

    def test_create_provider_openrouter(self) -> None:
        """Test that openrouter gets UniversalProvider."""
        provider = create_provider("openrouter", "sk-or-test")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "openrouter"

    def test_create_provider_cohere(self) -> None:
        """Test that cohere gets UniversalProvider."""
        provider = create_provider("cohere", "cohere-key-test")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "cohere"

    def test_create_provider_mistral(self) -> None:
        """Test that mistral gets UniversalProvider."""
        provider = create_provider("mistral", "mistral-key")
        assert isinstance(provider, UniversalProvider)
        assert provider.name == "mistral"

    def test_all_known_providers_covered(self) -> None:
        """Test that all providers from PROVIDER_ENDPOINTS are handled."""
        all_known = set(PROVIDER_ENDPOINTS.keys())
        handled = set(CUSTOM_PROVIDERS.keys()) | UNIVERSAL_PROVIDERS
        # Every known provider should be either custom or universal
        for provider in all_known:
            assert provider in handled, f"Provider '{provider}' is not handled by factory"

    def test_create_providers_from_keys_empty(self) -> None:
        """Test with no keys stored."""
        km = MagicMock(spec=KeyManager)
        km.get_active_providers.return_value = []
        providers = create_providers_from_keys(km)
        assert providers == []

    def test_create_providers_from_keys_multiple(self) -> None:
        """Test creating providers from multiple stored keys."""
        km = MagicMock(spec=KeyManager)
        km.get_active_providers.return_value = ["openai", "groq", "anthropic"]
        km.get_key.side_effect = lambda name: {
            "openai": "sk-test-openai",
            "groq": "gsk_test_groq",
            "anthropic": "sk-ant-test-anthropic",
        }[name]

        providers = create_providers_from_keys(km)
        assert len(providers) == 3

        provider_types = {p.name: type(p) for p in providers}
        assert provider_types["openai"] is OpenAIProvider
        assert provider_types["groq"] is UniversalProvider
        assert provider_types["anthropic"] is AnthropicProvider

    def test_create_providers_skips_none_keys(self) -> None:
        """Test that providers with None keys are skipped."""
        km = MagicMock(spec=KeyManager)
        km.get_active_providers.return_value = ["openai", "groq"]
        km.get_key.side_effect = lambda name: {
            "openai": "sk-test",
            "groq": None,
        }[name]

        providers = create_providers_from_keys(km)
        assert len(providers) == 1
        assert providers[0].name == "openai"

    def test_configure_router_from_keys(self) -> None:
        """Test building a complete router from keys."""
        km = MagicMock(spec=KeyManager)
        km.get_active_providers.return_value = ["openai", "together", "anthropic"]
        km.get_key.side_effect = lambda name: f"key-for-{name}"

        router = configure_router_from_keys(km)
        assert len(router.providers) == 3
        assert "openai" in router.providers
        assert "together" in router.providers
        assert "anthropic" in router.providers

    def test_configure_router_empty(self) -> None:
        """Test router with no keys returns empty router."""
        km = MagicMock(spec=KeyManager)
        km.get_active_providers.return_value = []

        router = configure_router_from_keys(km)
        assert len(router.providers) == 0


# --- Engine integration test ---


class TestEngineSetupLLMProviders:
    """Tests for engine.setup_llm_providers()."""

    def test_setup_llm_providers_with_keys(self, tmp_path: Any) -> None:
        """Test that setup_llm_providers configures the router."""
        # Write a test keys file
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(json.dumps({
            "keys": {
                "openai": ["sk-test-key-1"],
                "groq": ["gsk_test_key_2"],
            }
        }))

        from mk.core.engine import MKEngine
        engine = MKEngine()
        engine.setup_llm_providers(keys_file=str(keys_file))

        assert engine._llm_router is not None
        assert len(engine._llm_router.providers) == 2
        assert "openai" in engine._llm_router.providers
        assert "groq" in engine._llm_router.providers

    def test_setup_llm_providers_no_keys(self, tmp_path: Any) -> None:
        """Test that setup_llm_providers does nothing with no keys."""
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(json.dumps({"keys": {}}))

        from mk.core.engine import MKEngine
        engine = MKEngine()
        engine.setup_llm_providers(keys_file=str(keys_file))

        assert engine._llm_router is None

    def test_setup_llm_providers_missing_file(self, tmp_path: Any) -> None:
        """Test that setup_llm_providers handles missing keys file."""
        from mk.core.engine import MKEngine
        engine = MKEngine()
        engine.setup_llm_providers(keys_file=str(tmp_path / "nonexistent.json"))

        assert engine._llm_router is None
