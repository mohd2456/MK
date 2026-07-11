"""Unit tests for the LLM router.

Tests provider selection logic, fallback behavior, health tracking,
and usage statistics.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from mk.llm.base import LLMProvider, ProviderError
from mk.llm.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ProviderConfig,
    ProviderHealth,
)
from mk.llm.router import LLMRouter


def make_config(name: str, cost_input: float = 0.001, cost_output: float = 0.002) -> ProviderConfig:
    """Create a test provider config."""
    return ProviderConfig(
        name=name,
        api_key="test",
        base_url="http://test.local",
        default_model="test-model",
        cost_per_1k_input=cost_input,
        cost_per_1k_output=cost_output,
    )


class MockProvider(LLMProvider):
    """Mock provider for router testing."""

    def __init__(
        self,
        config: ProviderConfig,
        should_fail: bool = False,
        fail_count: int = 0,
    ) -> None:
        """Initialize mock provider."""
        super().__init__(config)
        self.should_fail = should_fail
        self.fail_count = fail_count
        self._calls = 0
        self.call_count = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Mock completion."""
        self.call_count += 1
        self._calls += 1
        if self.should_fail or (self.fail_count > 0 and self._calls <= self.fail_count):
            raise ProviderError(
                f"Mock failure from {self.name}",
                provider=self.name,
                retryable=True,
            )
        return LLMResponse(
            content=f"Response from {self.name}",
            tokens_used=10,
            input_tokens=6,
            output_tokens=4,
            cost_estimate=0.001,
            provider_used=self.name,
            model_used="test-model",
            latency_ms=50.0,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Mock stream."""
        yield f"chunk from {self.name}"

    async def health_check(self) -> bool:
        """Mock health check."""
        return not self.should_fail


def make_request() -> LLMRequest:
    """Create a simple test request."""
    return LLMRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="test")],
    )


class TestLLMRouter:
    """Tests for the LLM router."""

    async def test_register_provider(self) -> None:
        """Test registering providers."""
        router = LLMRouter()
        provider = MockProvider(make_config("test-1"))
        router.register_provider(provider)

        assert "test-1" in router.providers
        assert router.get_provider_status("test-1") is not None

    async def test_remove_provider(self) -> None:
        """Test removing providers."""
        router = LLMRouter()
        provider = MockProvider(make_config("test-1"))
        router.register_provider(provider)
        router.remove_provider("test-1")

        assert "test-1" not in router.providers

    async def test_select_healthy_provider(self) -> None:
        """Test that the router selects a healthy provider."""
        router = LLMRouter()
        p1 = MockProvider(make_config("cheap", cost_input=0.001))
        p2 = MockProvider(make_config("expensive", cost_input=0.01))
        router.register_provider(p1)
        router.register_provider(p2)

        response = await router.complete(make_request())
        assert response.content in ("Response from cheap", "Response from expensive")
        assert response.provider_used in ("cheap", "expensive")

    async def test_fallback_on_failure(self) -> None:
        """Test fallback to next provider when one fails."""
        router = LLMRouter()
        p1 = MockProvider(make_config("primary", cost_input=0.001), should_fail=True)
        p2 = MockProvider(make_config("backup", cost_input=0.002))
        router.register_provider(p1)
        router.register_provider(p2)

        response = await router.complete(make_request())
        assert response.provider_used == "backup"
        assert response.content == "Response from backup"

    async def test_all_providers_fail(self) -> None:
        """Test error when all providers fail."""
        router = LLMRouter()
        p1 = MockProvider(make_config("p1"), should_fail=True)
        p2 = MockProvider(make_config("p2"), should_fail=True)
        router.register_provider(p1)
        router.register_provider(p2)

        with pytest.raises(ProviderError):
            await router.complete(make_request())

    async def test_no_providers_registered(self) -> None:
        """Test error when no providers are available."""
        router = LLMRouter()

        with pytest.raises(ProviderError):
            await router.complete(make_request())

    async def test_provider_hint_preferred(self) -> None:
        """Test that provider_hint is tried first."""
        router = LLMRouter()
        p1 = MockProvider(make_config("cheap", cost_input=0.001))
        p2 = MockProvider(make_config("preferred", cost_input=0.01))
        router.register_provider(p1)
        router.register_provider(p2)

        request = make_request()
        request.provider_hint = "preferred"

        response = await router.complete(request)
        assert response.provider_used == "preferred"

    async def test_unhealthy_provider_skipped(self) -> None:
        """Test that unhealthy providers are skipped."""
        router = LLMRouter()
        p1 = MockProvider(make_config("unhealthy", cost_input=0.001))
        p2 = MockProvider(make_config("healthy", cost_input=0.002))
        router.register_provider(p1)
        router.register_provider(p2)

        # Mark p1 as unhealthy
        router.mark_provider_unhealthy("unhealthy")

        response = await router.complete(make_request())
        assert response.provider_used == "healthy"

    async def test_health_tracking_on_failure(self) -> None:
        """Test that provider health degrades on failures."""
        router = LLMRouter()
        p1 = MockProvider(make_config("flaky"), should_fail=True)
        p2 = MockProvider(make_config("stable"))
        router.register_provider(p1)
        router.register_provider(p2)

        # First request - p1 fails, falls back to p2
        await router.complete(make_request())

        status = router.get_provider_status("flaky")
        assert status is not None
        assert status.consecutive_failures >= 1
        assert status.health in (ProviderHealth.DEGRADED, ProviderHealth.UNHEALTHY)

    async def test_health_tracking_on_success(self) -> None:
        """Test that successful requests mark provider healthy."""
        router = LLMRouter()
        p1 = MockProvider(make_config("good"))
        router.register_provider(p1)

        await router.complete(make_request())

        status = router.get_provider_status("good")
        assert status is not None
        assert status.health == ProviderHealth.HEALTHY
        assert status.total_requests == 1

    async def test_multiple_failures_mark_unhealthy(self) -> None:
        """Test that 3 consecutive failures mark provider unhealthy."""
        router = LLMRouter()
        # Only register the unstable provider so all requests go to it
        p1 = MockProvider(make_config("unstable"), should_fail=True)
        router.register_provider(p1)

        # Make 3 requests - p1 fails each time
        for _ in range(3):
            try:
                await router.complete(make_request())
            except ProviderError:
                pass

        status = router.get_provider_status("unstable")
        assert status is not None
        assert status.health == ProviderHealth.UNHEALTHY
        assert status.consecutive_failures == 3

    async def test_mark_provider_healthy(self) -> None:
        """Test manually marking a provider healthy."""
        router = LLMRouter()
        p1 = MockProvider(make_config("test"))
        router.register_provider(p1)
        router.mark_provider_unhealthy("test")

        status = router.get_provider_status("test")
        assert status is not None
        assert status.health == ProviderHealth.UNHEALTHY

        router.mark_provider_healthy("test")
        status = router.get_provider_status("test")
        assert status is not None
        assert status.health == ProviderHealth.HEALTHY

    async def test_health_check_all(self) -> None:
        """Test running health checks on all providers."""
        router = LLMRouter()
        p1 = MockProvider(make_config("healthy-one"))
        p2 = MockProvider(make_config("failing-one"), should_fail=True)
        router.register_provider(p1)
        router.register_provider(p2)

        results = await router.health_check_all()
        assert results["healthy-one"] is True
        assert results["failing-one"] is False

    async def test_usage_stats(self) -> None:
        """Test usage statistics tracking."""
        router = LLMRouter()
        p1 = MockProvider(make_config("provider-a"))
        router.register_provider(p1)

        await router.complete(make_request())
        await router.complete(make_request())

        stats = router.get_usage_stats()
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 20
        assert stats["total_cost"] > 0
        assert "provider-a" in stats["providers"]

    async def test_cost_based_ordering(self) -> None:
        """Test that cheaper providers are preferred (all else equal)."""
        router = LLMRouter()
        # Register expensive first, cheap second
        p_expensive = MockProvider(make_config("expensive", cost_input=0.1))
        p_cheap = MockProvider(make_config("cheap", cost_input=0.001))
        router.register_provider(p_expensive)
        router.register_provider(p_cheap)

        response = await router.complete(make_request())
        # Cheap should be selected first since all are unknown/healthy
        assert response.provider_used == "cheap"

    async def test_degraded_provider_after_healthy(self) -> None:
        """Test that degraded providers are tried after healthy ones."""
        router = LLMRouter()
        p_degraded = MockProvider(make_config("degraded", cost_input=0.001))
        p_healthy = MockProvider(make_config("healthy", cost_input=0.01))
        router.register_provider(p_degraded)
        router.register_provider(p_healthy)

        # Manually set degraded status
        status = router.get_provider_status("degraded")
        assert status is not None
        status.health = ProviderHealth.DEGRADED
        status.consecutive_failures = 1

        response = await router.complete(make_request())
        # Healthy should be picked over degraded even though degraded is cheaper
        assert response.provider_used == "healthy"
