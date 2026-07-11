"""Anthropic Claude provider using httpx (no SDK dependency).

Supports the Messages API, tool use, and streaming.
Maps Claude's tool_use blocks to the unified ToolCall format.
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
    MessageRole,
    ProviderConfig,
    ToolCall,
    ToolDefinition,
)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using direct httpx calls.

    Supports Claude 3, Claude 3.5, and other Anthropic models.
    Uses the Messages API with tool use support.
    """

    API_VERSION = "2023-06-01"

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize Anthropic provider.

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
                    "x-api-key": self.config.api_key,
                    "anthropic-version": self.API_VERSION,
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    def _format_messages(self, messages: List[LLMMessage]) -> tuple:
        """Convert messages to Anthropic format (system separate from messages).

        Returns:
            Tuple of (system_prompt, messages_list).
        """
        system_prompt = ""
        formatted = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            else:
                role = "user" if msg.role in (MessageRole.USER, MessageRole.TOOL) else "assistant"
                formatted.append(
                    {
                        "role": role,
                        "content": msg.content,
                    }
                )

        return system_prompt, formatted

    def _format_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert tool definitions to Anthropic tool format."""
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters if tool.parameters else {"type": "object"},
                }
            )
        return formatted

    def _parse_response_content(self, content_blocks: List[Dict[str, Any]]) -> tuple:
        """Parse Anthropic response content blocks.

        Returns:
            Tuple of (text_content, tool_calls).
        """
        text_parts = []
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        return " ".join(text_parts), tool_calls

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Anthropic.

        Args:
            request: The LLM request.

        Returns:
            Unified LLMResponse.

        Raises:
            ProviderError: On failure after retries.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        system_prompt, messages = self._format_messages(request.messages)

        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if system_prompt:
            body["system"] = system_prompt

        if request.tools:
            body["tools"] = self._format_tools(request.tools)

        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                start = time.time()
                response = await client.post("/v1/messages", json=body)
                latency_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usage", {})
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)

                    content_blocks = data.get("content", [])
                    text_content, tool_calls = self._parse_response_content(content_blocks)

                    return LLMResponse(
                        content=text_content,
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
                    retry_after = float(response.headers.get("retry-after", str(2**attempt)))
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(self.name, retry_after)

                elif response.status_code == 401:
                    raise AuthenticationError(self.name)

                else:
                    error_msg = response.text
                    raise ProviderError(
                        f"Anthropic API error ({response.status_code}): {error_msg}",
                        provider=self.name,
                        status_code=response.status_code,
                        retryable=response.status_code >= 500,
                    )

            except httpx.TimeoutException:
                last_error = ProviderTimeoutError(self.name, self.config.timeout_seconds)
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
            except (RateLimitError, AuthenticationError, ProviderError):
                raise
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

        if last_error:
            if isinstance(last_error, ProviderError):
                raise last_error
            raise ProviderError(
                f"Anthropic request failed: {last_error}",
                provider=self.name,
                retryable=True,
            )
        raise ProviderError("Anthropic request failed", provider=self.name)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a completion response from Anthropic.

        Args:
            request: The LLM request.

        Yields:
            Text chunks as they arrive.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        system_prompt, messages = self._format_messages(request.messages)

        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }

        if system_prompt:
            body["system"] = system_prompt

        try:
            async with client.stream("POST", "/v1/messages", json=body) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(
                        f"Anthropic stream error ({response.status_code})",
                        provider=self.name,
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            event_type = data.get("type", "")
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, self.config.timeout_seconds)

    async def health_check(self) -> bool:
        """Check if Anthropic API is reachable.

        Returns:
            True if the API responds, False otherwise.
        """
        try:
            client = self._get_client()
            # Anthropic doesn't have a simple health endpoint,
            # so we send a minimal request
            response = await client.post(
                "/v1/messages",
                json={
                    "model": self.config.default_model or "claude-3-haiku-20240307",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
            )
            return response.status_code == 200
        except Exception:
            return False
