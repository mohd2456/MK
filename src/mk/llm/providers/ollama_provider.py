"""Local Ollama provider using httpx.

Connects to a local or remote Ollama instance. No API key needed.
Supports chat completions with tool calling (Ollama 0.3+).
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from mk.llm.base import LLMProvider, ProviderError
from mk.llm.base import TimeoutError as ProviderTimeoutError
from mk.llm.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ProviderConfig,
    ToolCall,
    ToolDefinition,
)


class OllamaProvider(LLMProvider):
    """Local Ollama provider using direct httpx calls.

    Connects to a local or remote Ollama instance for inference.
    No API key required - just a running Ollama server.
    """

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize Ollama provider.

        Args:
            config: Provider configuration (base_url is the Ollama server address).
        """
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers={"Content-Type": "application/json"},
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    def _format_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert LLMMessage list to Ollama API format."""
        formatted = []
        for msg in messages:
            formatted.append(
                {
                    "role": msg.role.value,
                    "content": msg.content,
                }
            )
        return formatted

    def _format_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert tool definitions to Ollama tool format."""
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return formatted

    def _parse_tool_calls(self, message: Dict[str, Any]) -> List[ToolCall]:
        """Parse tool calls from Ollama response."""
        calls = []
        raw_calls = message.get("tool_calls", [])
        for raw in raw_calls:
            func = raw.get("function", {})
            calls.append(
                ToolCall(
                    id=f"ollama_{func.get('name', '')}",
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {}),
                )
            )
        return calls

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Ollama.

        Args:
            request: The LLM request.

        Returns:
            Unified LLMResponse.

        Raises:
            ProviderError: On failure.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        body: Dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(request.messages),
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.tools:
            body["tools"] = self._format_tools(request.tools)

        try:
            start = time.time()
            response = await client.post("/api/chat", json=body)
            latency_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                message = data.get("message", {})

                # Ollama provides eval_count and prompt_eval_count
                input_tokens = data.get("prompt_eval_count", 0)
                output_tokens = data.get("eval_count", 0)

                tool_calls = self._parse_tool_calls(message)

                return LLMResponse(
                    content=message.get("content", ""),
                    tool_calls=tool_calls,
                    tokens_used=input_tokens + output_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate=0.0,  # Local inference is free
                    provider_used=self.name,
                    model_used=model,
                    latency_ms=latency_ms,
                )

            else:
                error_msg = response.text
                raise ProviderError(
                    f"Ollama API error ({response.status_code}): {error_msg}",
                    provider=self.name,
                    status_code=response.status_code,
                    retryable=response.status_code >= 500,
                )

        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, self.config.timeout_seconds)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Ollama request failed: {e}",
                provider=self.name,
                retryable=True,
            )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a completion response from Ollama.

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
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        try:
            async with client.stream("POST", "/api/chat", json=body) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(
                        f"Ollama stream error ({response.status_code})",
                        provider=self.name,
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        message = data.get("message", {})
                        content = message.get("content", "")
                        if content:
                            yield content
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, self.config.timeout_seconds)

    async def health_check(self) -> bool:
        """Check if Ollama server is reachable.

        Returns:
            True if the server responds, False otherwise.
        """
        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False
