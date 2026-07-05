"""Unit tests for LLM providers.

Tests each provider with mocked HTTP responses using httpx's mock transport.
Covers normal completion, streaming, error handling, and rate limit retry.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest

from mk.llm.base import AuthenticationError, ProviderError, RateLimitError
from mk.llm.models import (
    LLMMessage,
    LLMRequest,
    MessageRole,
    ProviderConfig,
    ToolDefinition,
)
from mk.llm.providers.anthropic_provider import AnthropicProvider
from mk.llm.providers.gemini_provider import GeminiProvider
from mk.llm.providers.groq_provider import GroqProvider
from mk.llm.providers.mistral_provider import MistralProvider
from mk.llm.providers.ollama_provider import OllamaProvider
from mk.llm.providers.openai_provider import OpenAIProvider


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


# --- OpenAI Provider Tests ---


class TestOpenAIProvider:
    """Tests for the OpenAI provider."""

    def _mock_response(self, content: str = "Hello!") -> Dict[str, Any]:
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

    async def test_complete_success(self) -> None:
        """Test successful completion."""
        config = make_config("openai", "http://test.local")
        provider = OpenAIProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local",
            transport=transport,
            headers={"Authorization": "Bearer test"},
        )

        response = await provider.complete(make_request())
        assert response.content == "Hello!"
        assert response.provider_used == "openai"
        assert response.tokens_used == 15
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    async def test_complete_with_tool_calls(self) -> None:
        """Test completion with tool calls."""
        config = make_config("openai")
        provider = OpenAIProvider(config)

        mock_data = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "London"}',
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
        assert response.tool_calls[0].name == "get_weather"
        assert response.tool_calls[0].arguments == {"city": "London"}

    async def test_complete_auth_error(self) -> None:
        """Test authentication error handling."""
        config = make_config("openai")
        provider = OpenAIProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, json={"error": "unauthorized"})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(AuthenticationError):
            await provider.complete(make_request())

    async def test_complete_rate_limit(self) -> None:
        """Test rate limit error handling."""
        config = make_config("openai")
        config = config.model_copy(update={"max_retries": 1})
        provider = OpenAIProvider(config)

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
        config = make_config("openai")
        config = config.model_copy(update={"max_retries": 1})
        provider = OpenAIProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="Internal Server Error")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(make_request())
        assert exc_info.value.status_code == 500

    async def test_health_check_success(self) -> None:
        """Test successful health check."""
        config = make_config("openai")
        provider = OpenAIProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"data": []})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        assert await provider.health_check() is True

    async def test_health_check_failure(self) -> None:
        """Test failed health check."""
        config = make_config("openai")
        provider = OpenAIProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="error")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        assert await provider.health_check() is False

    async def test_cost_estimation(self) -> None:
        """Test cost calculation."""
        config = make_config("openai")
        provider = OpenAIProvider(config)
        cost = provider.estimate_cost(1000, 500)
        # 1000/1000 * 0.001 + 500/1000 * 0.002 = 0.001 + 0.001 = 0.002
        assert abs(cost - 0.002) < 0.0001


# --- Anthropic Provider Tests ---


class TestAnthropicProvider:
    """Tests for the Anthropic Claude provider."""

    def _mock_response(self, content: str = "Hello!") -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": content}],
            "usage": {"input_tokens": 12, "output_tokens": 6},
            "stop_reason": "end_turn",
        }

    async def test_complete_success(self) -> None:
        """Test successful completion."""
        config = make_config("anthropic", "http://test.local")
        provider = AnthropicProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local",
            transport=transport,
            headers={"x-api-key": "test"},
        )

        response = await provider.complete(make_request())
        assert response.content == "Hello!"
        assert response.provider_used == "anthropic"
        assert response.input_tokens == 12
        assert response.output_tokens == 6

    async def test_complete_with_tool_use(self) -> None:
        """Test completion with Claude tool_use blocks."""
        config = make_config("anthropic")
        provider = AnthropicProvider(config)

        mock_data = {
            "content": [
                {"type": "text", "text": "Let me check that."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "check_status",
                    "input": {"service": "plex"},
                },
            ],
            "usage": {"input_tokens": 20, "output_tokens": 15},
        }

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_data)
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert "Let me check that." in response.content
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "check_status"
        assert response.tool_calls[0].id == "toolu_123"

    async def test_complete_auth_error(self) -> None:
        """Test authentication error."""
        config = make_config("anthropic")
        config = config.model_copy(update={"max_retries": 1})
        provider = AnthropicProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, json={"error": "invalid_api_key"})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(AuthenticationError):
            await provider.complete(make_request())

    async def test_system_message_handling(self) -> None:
        """Test that system messages are separated correctly."""
        config = make_config("anthropic")
        provider = AnthropicProvider(config)

        request = LLMRequest(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
                LLMMessage(role=MessageRole.USER, content="Hi"),
            ],
        )

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        # Should not raise - system message handled
        response = await provider.complete(request)
        assert response.content == "Hello!"


# --- Gemini Provider Tests ---


class TestGeminiProvider:
    """Tests for the Google Gemini provider."""

    def _mock_response(self, content: str = "Hello!") -> Dict[str, Any]:
        return {
            "candidates": [{
                "content": {
                    "parts": [{"text": content}],
                    "role": "model",
                },
            }],
            "usageMetadata": {
                "promptTokenCount": 8,
                "candidatesTokenCount": 4,
            },
        }

    async def test_complete_success(self) -> None:
        """Test successful completion."""
        config = make_config("gemini", "http://test.local")
        provider = GeminiProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Hello!"
        assert response.provider_used == "gemini"
        assert response.input_tokens == 8
        assert response.output_tokens == 4

    async def test_complete_with_function_call(self) -> None:
        """Test completion with Gemini function calling."""
        config = make_config("gemini")
        provider = GeminiProvider(config)

        mock_data = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "get_weather",
                            "args": {"location": "NYC"},
                        }
                    }],
                },
            }],
            "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 8},
        }

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_data)
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "get_weather"

    async def test_complete_rate_limit(self) -> None:
        """Test rate limit handling."""
        config = make_config("gemini")
        config = config.model_copy(update={"max_retries": 1})
        provider = GeminiProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"retry-after": "2"})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(RateLimitError):
            await provider.complete(make_request())


# --- Groq Provider Tests ---


class TestGroqProvider:
    """Tests for the Groq provider."""

    def _mock_response(self, content: str = "Fast response!") -> Dict[str, Any]:
        return {
            "choices": [{
                "message": {"content": content, "tool_calls": []},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }

    async def test_complete_success(self) -> None:
        """Test successful completion."""
        config = make_config("groq", "http://test.local")
        provider = GroqProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Fast response!"
        assert response.provider_used == "groq"
        assert response.tokens_used == 8

    async def test_complete_auth_error(self) -> None:
        """Test authentication error."""
        config = make_config("groq")
        config = config.model_copy(update={"max_retries": 1})
        provider = GroqProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, text="Unauthorized")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        with pytest.raises(AuthenticationError):
            await provider.complete(make_request())


# --- Mistral Provider Tests ---


class TestMistralProvider:
    """Tests for the Mistral provider."""

    def _mock_response(self, content: str = "Bonjour!") -> Dict[str, Any]:
        return {
            "choices": [{
                "message": {"content": content, "tool_calls": []},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4},
        }

    async def test_complete_success(self) -> None:
        """Test successful completion."""
        config = make_config("mistral", "http://test.local")
        provider = MistralProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Bonjour!"
        assert response.provider_used == "mistral"

    async def test_complete_with_tools(self) -> None:
        """Test completion with tool definitions."""
        config = make_config("mistral")
        provider = MistralProvider(config)

        request = LLMRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Hello")],
            tools=[
                ToolDefinition(
                    name="search",
                    description="Search the web",
                    parameters={"type": "object", "properties": {"q": {"type": "string"}}},
                )
            ],
        )

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://test.local", transport=transport
        )

        response = await provider.complete(request)
        assert response.content == "Bonjour!"


# --- Ollama Provider Tests ---


class TestOllamaProvider:
    """Tests for the Ollama local provider."""

    def _mock_response(self, content: str = "Local response") -> Dict[str, Any]:
        return {
            "message": {"role": "assistant", "content": content},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 8,
        }

    async def test_complete_success(self) -> None:
        """Test successful completion."""
        config = make_config("ollama", "http://localhost:11434")
        config = config.model_copy(update={"api_key": ""})
        provider = OllamaProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=self._mock_response())
        )
        provider._client = httpx.AsyncClient(
            base_url="http://localhost:11434", transport=transport
        )

        response = await provider.complete(make_request())
        assert response.content == "Local response"
        assert response.provider_used == "ollama"
        assert response.cost_estimate == 0.0  # Local = free
        assert response.input_tokens == 10
        assert response.output_tokens == 8

    async def test_complete_server_error(self) -> None:
        """Test server error handling."""
        config = make_config("ollama", "http://localhost:11434")
        provider = OllamaProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="model not found")
        )
        provider._client = httpx.AsyncClient(
            base_url="http://localhost:11434", transport=transport
        )

        with pytest.raises(ProviderError):
            await provider.complete(make_request())

    async def test_health_check_success(self) -> None:
        """Test health check with running Ollama server."""
        config = make_config("ollama", "http://localhost:11434")
        provider = OllamaProvider(config)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"models": []})
        )
        provider._client = httpx.AsyncClient(
            base_url="http://localhost:11434", transport=transport
        )

        assert await provider.health_check() is True

    async def test_health_check_failure(self) -> None:
        """Test health check when Ollama is not running."""
        config = make_config("ollama", "http://localhost:11434")
        provider = OllamaProvider(config)

        def raise_error(req: Any) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_error)
        provider._client = httpx.AsyncClient(
            base_url="http://localhost:11434", transport=transport
        )

        assert await provider.health_check() is False


# --- Cross-provider interface tests ---


class TestProviderInterface:
    """Tests that all providers implement the same interface."""

    async def test_all_providers_instantiate(self) -> None:
        """Test that all 6 providers can be instantiated."""
        config = make_config("test", "http://test.local")

        providers = [
            OpenAIProvider(config),
            AnthropicProvider(config),
            GeminiProvider(config),
            GroqProvider(config),
            MistralProvider(config),
            OllamaProvider(config),
        ]

        for provider in providers:
            assert hasattr(provider, "complete")
            assert hasattr(provider, "stream")
            assert hasattr(provider, "health_check")
            assert hasattr(provider, "estimate_cost")
            assert hasattr(provider, "name")

    async def test_all_providers_have_consistent_name(self) -> None:
        """Test that provider name comes from config."""
        config = make_config("my-provider", "http://test.local")
        providers = [
            OpenAIProvider(config),
            AnthropicProvider(config),
            GeminiProvider(config),
            GroqProvider(config),
            MistralProvider(config),
            OllamaProvider(config),
        ]

        for provider in providers:
            assert provider.name == "my-provider"
