"""Data models for the LLM integration layer.

Defines request/response structures and provider configuration used
across all LLM providers and the routing system.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role for messages sent to LLM providers."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """A single message in an LLM conversation."""

    role: MessageRole = Field(description="Message role")
    content: str = Field(description="Message content")
    name: Optional[str] = Field(default=None, description="Tool name for tool messages")
    tool_call_id: Optional[str] = Field(default=None, description="ID for tool result messages")


class ToolDefinition(BaseModel):
    """Definition of a tool available to the LLM."""

    name: str = Field(description="Tool name")
    description: str = Field(description="Tool description")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema of parameters"
    )


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""

    id: str = Field(description="Unique tool call ID")
    name: str = Field(description="Tool name to invoke")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class LLMRequest(BaseModel):
    """Request to send to an LLM provider."""

    messages: List[LLMMessage] = Field(description="Conversation messages")
    max_tokens: int = Field(default=4096, description="Maximum tokens in response")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    tools: Optional[List[ToolDefinition]] = Field(
        default=None, description="Available tools for function calling"
    )
    provider_hint: Optional[str] = Field(
        default=None, description="Preferred provider name (hint, not mandate)"
    )
    model_override: Optional[str] = Field(
        default=None, description="Override the provider's default model"
    )


class LLMResponse(BaseModel):
    """Unified response from any LLM provider."""

    content: str = Field(default="", description="Text response content")
    tool_calls: List[ToolCall] = Field(
        default_factory=list, description="Tool calls requested by the LLM"
    )
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    input_tokens: int = Field(default=0, description="Input/prompt tokens")
    output_tokens: int = Field(default=0, description="Output/completion tokens")
    cost_estimate: float = Field(default=0.0, description="Estimated cost in USD")
    provider_used: str = Field(default="", description="Provider that handled this request")
    model_used: str = Field(default="", description="Model that generated this response")
    latency_ms: float = Field(default=0.0, description="Response latency in milliseconds")
    cached: bool = Field(default=False, description="Whether this was served from cache")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ProviderHealth(str, Enum):
    """Health status of a provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    name: str = Field(description="Provider identifier (e.g., 'openai', 'anthropic')")
    api_key: str = Field(default="", description="API key for authentication")
    base_url: str = Field(description="Base URL for the API")
    models: List[str] = Field(default_factory=list, description="Available models")
    default_model: str = Field(default="", description="Default model to use")
    rate_limit_rpm: int = Field(default=60, description="Rate limit: requests per minute")
    rate_limit_tpm: int = Field(default=100000, description="Rate limit: tokens per minute")
    cost_per_1k_input: float = Field(default=0.0, description="Cost per 1K input tokens (USD)")
    cost_per_1k_output: float = Field(default=0.0, description="Cost per 1K output tokens (USD)")
    timeout_seconds: float = Field(default=60.0, description="Request timeout")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    enabled: bool = Field(default=True, description="Whether this provider is enabled")


class ProviderStatus(BaseModel):
    """Runtime status of a provider."""

    name: str = Field(description="Provider name")
    health: ProviderHealth = Field(default=ProviderHealth.UNKNOWN)
    last_success: Optional[datetime] = Field(default=None)
    last_failure: Optional[datetime] = Field(default=None)
    consecutive_failures: int = Field(default=0)
    total_requests: int = Field(default=0)
    total_tokens: int = Field(default=0)
    total_cost: float = Field(default=0.0)
    avg_latency_ms: float = Field(default=0.0)
