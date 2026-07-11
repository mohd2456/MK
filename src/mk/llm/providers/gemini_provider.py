"""Google Gemini provider using httpx (no SDK dependency).

Supports the generateContent API, function calling, and streaming.
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


class GeminiProvider(LLMProvider):
    """Google Gemini provider using direct httpx calls.

    Supports Gemini Pro, Gemini Ultra, and other Google AI models.
    Uses the generateContent API with function calling support.
    """

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize Gemini provider.

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
                headers={"Content-Type": "application/json"},
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    def _format_contents(self, messages: List[LLMMessage]) -> tuple:
        """Convert messages to Gemini format.

        Returns:
            Tuple of (system_instruction, contents_list).
        """
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_instruction = {"parts": [{"text": msg.content}]}
            else:
                role = "user" if msg.role in (MessageRole.USER, MessageRole.TOOL) else "model"
                contents.append(
                    {
                        "role": role,
                        "parts": [{"text": msg.content}],
                    }
                )

        return system_instruction, contents

    def _format_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert tool definitions to Gemini function declarations."""
        declarations = []
        for tool in tools:
            declarations.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters if tool.parameters else {"type": "object"},
                }
            )
        return [{"functionDeclarations": declarations}]

    def _parse_response(self, data: Dict[str, Any]) -> tuple:
        """Parse Gemini response data.

        Returns:
            Tuple of (text_content, tool_calls, token_counts).
        """
        text_parts = []
        tool_calls = []

        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            for part in parts:
                if "text" in part:
                    text_parts.append(part["text"])
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append(
                        ToolCall(
                            id=f"gemini_{fc.get('name', '')}",
                            name=fc.get("name", ""),
                            arguments=fc.get("args", {}),
                        )
                    )

        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return " ".join(text_parts), tool_calls, (input_tokens, output_tokens)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Gemini.

        Args:
            request: The LLM request.

        Returns:
            Unified LLMResponse.

        Raises:
            ProviderError: On failure after retries.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        system_instruction, contents = self._format_contents(request.messages)

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }

        if system_instruction:
            body["systemInstruction"] = system_instruction

        if request.tools:
            body["tools"] = self._format_tools(request.tools)

        url = f"/v1beta/models/{model}:generateContent?key={self.config.api_key}"

        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                start = time.time()
                response = await client.post(url, json=body)
                latency_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    text_content, tool_calls, (input_tokens, output_tokens) = self._parse_response(
                        data
                    )

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

                elif response.status_code in (401, 403):
                    raise AuthenticationError(self.name)

                else:
                    error_msg = response.text
                    raise ProviderError(
                        f"Gemini API error ({response.status_code}): {error_msg}",
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
                f"Gemini request failed: {last_error}",
                provider=self.name,
                retryable=True,
            )
        raise ProviderError("Gemini request failed", provider=self.name)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a completion response from Gemini.

        Args:
            request: The LLM request.

        Yields:
            Text chunks as they arrive.
        """
        client = self._get_client()
        model = request.model_override or self.config.default_model

        system_instruction, contents = self._format_contents(request.messages)

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }

        if system_instruction:
            body["systemInstruction"] = system_instruction

        url = f"/v1beta/models/{model}:streamGenerateContent?key={self.config.api_key}&alt=sse"

        try:
            async with client.stream("POST", url, json=body) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(
                        f"Gemini stream error ({response.status_code})",
                        provider=self.name,
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    if "text" in part:
                                        yield part["text"]
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, self.config.timeout_seconds)

    async def health_check(self) -> bool:
        """Check if Gemini API is reachable.

        Returns:
            True if the API responds, False otherwise.
        """
        try:
            client = self._get_client()
            model = self.config.default_model or "gemini-pro"
            url = f"/v1beta/models/{model}?key={self.config.api_key}"
            response = await client.get(url)
            return response.status_code == 200
        except Exception:
            return False
