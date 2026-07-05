"""Mistral provider using httpx (no SDK dependency).

Supports chat completions with tool use via the Mistral API.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from mk.llm.base import (
    AuthenticationError,
    LLMProvider,
    ProviderError,
    RateLimitError,
)
from mk.llm.base import TimeoutError as ProviderTimeoutError
from mk.llm.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ProviderConfig,
    ToolCall,
    ToolDefinition,
)


class MistralProvider(LLMProvider):
    """Mistral AI provider using direct httpx calls.

    Supports Mistral Large, Medium, Small, and other models.
    Uses the chat completions API with tool calling support.
    """

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize Mistral provider.

        Args:
            config: Provider configuration with API key and settings.
        """
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    def _format_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert LLMMessage list to Mistral API format."""
        formatted = []
        for msg in messages:
            formatted.append({
                "role": msg.role.value,
                "content": msg.content,
            })
        return formatted

    def _format_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert tool definitions to Mistral function calling format."""
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return formatted

    def _parse_tool_calls(self, raw_calls: List[Dict[str, Any]]) -> List[ToolCall]:
        """Parse tool calls from response."""
        calls = []
        for raw in raw_calls:
            args_str = raw.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except (json.JSONDecodeError, TypeError):
                args = {}
            calls.append(ToolCall(
                id=raw.get("id", ""),
                name=raw.get("function", {}).get("name", ""),
                arguments=args,
            ))
        return calls

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Mistral.

        Args:
            request: The LLM request.

        Returns:
            Unified LLMResponse.

        Raises:
            ProviderError: On failure after retries.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        body: Dict[str, Any] = {
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
                response = await client.post("/v1/chat/completions", json=body)
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
                        f"Mistral API error ({response.status_code}): {error_msg}",
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
                f"Mistral request failed: {last_error}",
                provider=self.name,
                retryable=True,
            )
        raise ProviderError("Mistral request failed", provider=self.name)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a completion response from Mistral.

        Args:
            request: The LLM request.

        Yields:
            Text chunks as they arrive.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        body: Dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(request.messages),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }

        try:
            async with client.stream("POST", "/v1/chat/completions", json=body) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(
                        f"Mistral stream error ({response.status_code})",
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
        """Check if Mistral API is reachable.

        Returns:
            True if the API responds, False otherwise.
        """
        try:
            client = self._get_client()
            response = await client.get("/v1/models")
            return response.status_code == 200
        except Exception:
            return False
