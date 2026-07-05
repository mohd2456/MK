"""Abstract base class for all LLM providers.

Every LLM provider (OpenAI, Anthropic, Gemini, Groq, Mistral, Ollama)
must implement this interface. This ensures the router can treat all
providers equally with no special handling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from mk.llm.models import LLMRequest, LLMResponse, ProviderConfig


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All providers implement the same interface so the router can
    switch between them transparently. No provider gets special treatment.
    """

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize the provider with its configuration.

        Args:
            config: Provider-specific configuration including API key,
                base URL, models, and rate limits.
        """
        self.config = config

    @property
    def name(self) -> str:
        """Return the provider name."""
        return self.config.name

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the provider.

        Args:
            request: The LLM request with messages, parameters, and tools.

        Returns:
            Unified LLMResponse with content, tool calls, usage, and cost.

        Raises:
            ProviderError: If the request fails after retries.
        """
        ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a completion response token by token.

        Args:
            request: The LLM request with messages and parameters.

        Yields:
            Individual tokens/chunks as they arrive.

        Raises:
            ProviderError: If the stream fails.
        """
        ...
        # Make this an async generator
        yield ""  # pragma: no cover

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is reachable and responding.

        Returns:
            True if the provider is healthy, False otherwise.
        """
        ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost for a given number of tokens.

        Args:
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.

        Returns:
            Estimated cost in USD.
        """
        input_cost = (input_tokens / 1000.0) * self.config.cost_per_1k_input
        output_cost = (output_tokens / 1000.0) * self.config.cost_per_1k_output
        return input_cost + output_cost


class ProviderError(Exception):
    """Base exception for provider errors."""

    def __init__(
        self,
        message: str,
        provider: str = "",
        status_code: int = 0,
        retryable: bool = False,
    ) -> None:
        """Initialize the provider error.

        Args:
            message: Error description.
            provider: Provider that raised the error.
            status_code: HTTP status code if applicable.
            retryable: Whether the request should be retried.
        """
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class RateLimitError(ProviderError):
    """Raised when a provider rate limit is hit."""

    def __init__(self, provider: str, retry_after: float = 0.0) -> None:
        """Initialize rate limit error.

        Args:
            provider: Provider that rate limited us.
            retry_after: Seconds to wait before retrying.
        """
        super().__init__(
            f"Rate limited by {provider}",
            provider=provider,
            status_code=429,
            retryable=True,
        )
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """Raised when authentication fails."""

    def __init__(self, provider: str) -> None:
        """Initialize auth error.

        Args:
            provider: Provider that rejected auth.
        """
        super().__init__(
            f"Authentication failed for {provider}",
            provider=provider,
            status_code=401,
            retryable=False,
        )


class TimeoutError(ProviderError):
    """Raised when a request times out."""

    def __init__(self, provider: str, timeout: float) -> None:
        """Initialize timeout error.

        Args:
            provider: Provider that timed out.
            timeout: Timeout duration in seconds.
        """
        super().__init__(
            f"Request to {provider} timed out after {timeout}s",
            provider=provider,
            status_code=408,
            retryable=True,
        )
