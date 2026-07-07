"""Universal OpenAI-compatible provider.

Handles all providers that expose an OpenAI-compatible chat completions API:
Groq, Together, Fireworks, DeepSeek, Perplexity, OpenRouter, Cohere, Mistral.

Each provider just needs a different base URL and (optionally) a different
chat completions endpoint path. The request/response format is identical
to OpenAI's /v1/chat/completions.
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from mk.llm.models import LLMRequest, LLMResponse, ProviderConfig
from mk.llm.providers.openai_provider import OpenAIProvider


# Endpoint path overrides for providers that differ from the standard /v1/chat/completions.
# Most OpenAI-compatible providers use /v1/chat/completions with the base_url already
# containing the prefix (e.g. https://api.groq.com/openai/v1).
# For providers where the base_url does NOT contain /v1 but the endpoint needs it,
# we set the full path here.
CHAT_COMPLETIONS_PATHS = {
    "groq": "/openai/v1/chat/completions",
    "perplexity": "/chat/completions",
}

MODELS_PATHS = {
    "groq": "/openai/v1/models",
    "perplexity": "/models",
}


class UniversalProvider(OpenAIProvider):
    """OpenAI-compatible provider for any service using the same API format.

    Extends OpenAIProvider with configurable endpoint paths. Works with:
    - Groq (fast inference on LPUs)
    - Together AI (open-source model hosting)
    - Fireworks AI (fast open-source inference)
    - DeepSeek (reasoning models)
    - Perplexity (search-augmented models)
    - OpenRouter (multi-provider routing)
    - Cohere (enterprise NLP, OpenAI-compatible endpoint)
    - Mistral (European AI lab)

    All these providers accept the same request format as OpenAI and return
    the same response format (choices, usage, tool_calls).
    """

    def __init__(self, config: ProviderConfig, chat_path: Optional[str] = None, models_path: Optional[str] = None) -> None:
        """Initialize the universal provider.

        Args:
            config: Provider configuration with base_url, api_key, etc.
            chat_path: Override for the chat completions endpoint path.
                If None, uses the default path for the provider name or /v1/chat/completions.
            models_path: Override for the models list endpoint path.
                If None, uses the default path for the provider name or /v1/models.
        """
        super().__init__(config)
        self._chat_path = chat_path or CHAT_COMPLETIONS_PATHS.get(config.name, "/v1/chat/completions")
        self._models_path = models_path or MODELS_PATHS.get(config.name, "/v1/models")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request using the configured chat endpoint.

        Args:
            request: The LLM request.

        Returns:
            Unified LLMResponse.

        Raises:
            ProviderError: On failure after retries.
        """
        import asyncio
        import time

        import httpx

        from mk.llm.base import (
            AuthenticationError,
            ProviderError,
            RateLimitError,
        )
        from mk.llm.base import TimeoutError as ProviderTimeoutError

        client = self._get_client()
        model = request.model_override or self.config.default_model

        body = {
            "model": model,
            "messages": self._format_messages(request.messages),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.tools:
            body["tools"] = self._format_tools(request.tools)

        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                start = time.time()
                response = await client.post(self._chat_path, json=body)
                latency_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    usage = data.get("usage", {})

                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)

                    tool_calls = self._parse_tool_calls(
                        message.get("tool_calls", [])
                    )

                    return LLMResponse(
                        content=message.get("content", "") or "",
                        tool_calls=tool_calls,
                        tokens_used=input_tokens + output_tokens,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_estimate=self.estimate_cost(input_tokens, output_tokens),
                        provider_used=self.name,
                        model_used=model,
                        latency_ms=latency_ms,
                    )

                elif response.status_code == 429:
                    retry_after = float(
                        response.headers.get("retry-after", str(2 ** attempt))
                    )
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(self.name, retry_after)

                elif response.status_code == 401:
                    raise AuthenticationError(self.name)

                else:
                    error_msg = response.text
                    raise ProviderError(
                        f"{self.name} API error ({response.status_code}): {error_msg}",
                        provider=self.name,
                        status_code=response.status_code,
                        retryable=response.status_code >= 500,
                    )

            except httpx.TimeoutException:
                last_error = ProviderTimeoutError(self.name, self.config.timeout_seconds)
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except (RateLimitError, AuthenticationError, ProviderError):
                raise
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue

        if last_error:
            if isinstance(last_error, ProviderError):
                raise last_error
            raise ProviderError(
                f"{self.name} request failed: {last_error}",
                provider=self.name,
                retryable=True,
            )
        raise ProviderError(f"{self.name} request failed", provider=self.name)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a completion response using the configured chat endpoint.

        Args:
            request: The LLM request.

        Yields:
            Text chunks as they arrive.
        """
        import json

        import httpx

        from mk.llm.base import ProviderError
        from mk.llm.base import TimeoutError as ProviderTimeoutError

        client = self._get_client()
        model = request.model_override or self.config.default_model

        body = {
            "model": model,
            "messages": self._format_messages(request.messages),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }

        try:
            async with client.stream("POST", self._chat_path, json=body) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(
                        f"{self.name} stream error ({response.status_code})",
                        provider=self.name,
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, self.config.timeout_seconds)

    async def health_check(self) -> bool:
        """Check if the API is reachable by listing models.

        Returns:
            True if the API responds, False otherwise.
        """
        try:
            client = self._get_client()
            response = await client.get(self._models_path)
            return response.status_code == 200
        except Exception:
            return False
