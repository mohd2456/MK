"""Intelligent LLM provider router.

Maintains health status of all configured providers, picks the best
available based on health, cost efficiency, and model capability.
Supports fallback chains with no loyalty to any single provider.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mk.llm.base import LLMProvider, ProviderError
from mk.llm.compression import ContextCompressor
from mk.llm.models import (
    LLMRequest,
    LLMResponse,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class LLMRouter:
    """Intelligent multi-provider LLM router.

    All providers are equal - no main provider, no loyalty. The router
    selects the best available provider based on:
    1. Provider health (must be healthy or degraded)
    2. Cost efficiency (lower cost preferred)
    3. Recent performance (latency, success rate)

    Supports automatic fallback when a provider fails.
    """

    def __init__(self, compressor: Optional[ContextCompressor] = None) -> None:
        """Initialize the router with empty provider registry.

        Args:
            compressor: Optional context compressor. If omitted, one is built
                from the environment (disabled unless ``MK_COMPRESSION`` is set),
                so default behavior is unchanged.
        """
        self._providers: Dict[str, LLMProvider] = {}
        self._status: Dict[str, ProviderStatus] = {}
        self._fallback_chain: List[str] = []
        self._compressor = compressor or ContextCompressor.from_env()

    def register_provider(self, provider: LLMProvider) -> None:
        """Register a provider with the router.

        Args:
            provider: An LLMProvider instance to register.
        """
        self._providers[provider.name] = provider
        self._status[provider.name] = ProviderStatus(
            name=provider.name,
            health=ProviderHealth.UNKNOWN,
        )
        # Rebuild fallback chain when providers change
        self._rebuild_fallback_chain()

    def remove_provider(self, name: str) -> None:
        """Remove a provider from the router.

        Args:
            name: Name of the provider to remove.
        """
        self._providers.pop(name, None)
        self._status.pop(name, None)
        self._rebuild_fallback_chain()

    def _rebuild_fallback_chain(self) -> None:
        """Rebuild the fallback chain based on cost and health."""
        # Sort by cost (lower first), then by health
        providers = list(self._providers.values())
        providers.sort(key=lambda p: p.config.cost_per_1k_input)
        self._fallback_chain = [p.name for p in providers]

    @property
    def providers(self) -> Dict[str, LLMProvider]:
        """Return registered providers."""
        return dict(self._providers)

    @property
    def provider_statuses(self) -> Dict[str, ProviderStatus]:
        """Return current provider health statuses."""
        return dict(self._status)

    def get_provider_status(self, name: str) -> Optional[ProviderStatus]:
        """Get the status of a specific provider.

        Args:
            name: Provider name.

        Returns:
            ProviderStatus or None if not found.
        """
        return self._status.get(name)

    def _select_provider(self, request: LLMRequest) -> List[str]:
        """Select providers to try, ordered by preference.

        Selection logic:
        1. If provider_hint is set and healthy, try it first
        2. Then try healthy providers sorted by cost efficiency
        3. Fall back to degraded providers
        4. Skip unhealthy providers

        Args:
            request: The LLM request (may contain provider_hint).

        Returns:
            Ordered list of provider names to try.
        """
        candidates: List[str] = []

        # If there's a hint, put it first (if available and not unhealthy)
        if request.provider_hint and request.provider_hint in self._providers:
            status = self._status.get(request.provider_hint)
            if status and status.health != ProviderHealth.UNHEALTHY:
                candidates.append(request.provider_hint)

        # Separate healthy and degraded providers
        healthy = []
        degraded = []

        for name in self._fallback_chain:
            if name in candidates:
                continue  # Already added as hint
            status = self._status.get(name)
            if status is None:
                healthy.append(name)  # Unknown = give it a chance
            elif status.health in (ProviderHealth.HEALTHY, ProviderHealth.UNKNOWN):
                healthy.append(name)
            elif status.health == ProviderHealth.DEGRADED:
                degraded.append(name)
            # Skip UNHEALTHY

        candidates.extend(healthy)
        candidates.extend(degraded)
        return candidates

    def _update_status_success(
        self, name: str, latency_ms: float, tokens: int, cost: float
    ) -> None:
        """Update provider status after a successful request."""
        status = self._status.get(name)
        if status is None:
            return

        status.health = ProviderHealth.HEALTHY
        status.last_success = datetime.utcnow()
        status.consecutive_failures = 0
        status.total_requests += 1
        status.total_tokens += tokens
        status.total_cost += cost

        # Update rolling average latency
        if status.avg_latency_ms == 0:
            status.avg_latency_ms = latency_ms
        else:
            # Exponential moving average
            status.avg_latency_ms = 0.8 * status.avg_latency_ms + 0.2 * latency_ms

    def _update_status_failure(self, name: str, error: Exception) -> None:
        """Update provider status after a failed request."""
        status = self._status.get(name)
        if status is None:
            return

        status.last_failure = datetime.utcnow()
        status.consecutive_failures += 1
        status.total_requests += 1

        # Degrade or mark unhealthy based on consecutive failures
        if status.consecutive_failures >= 3:
            status.health = ProviderHealth.UNHEALTHY
        elif status.consecutive_failures >= 1:
            status.health = ProviderHealth.DEGRADED

    def mark_provider_healthy(self, name: str) -> None:
        """Manually mark a provider as healthy.

        Args:
            name: Provider name to mark healthy.
        """
        status = self._status.get(name)
        if status:
            status.health = ProviderHealth.HEALTHY
            status.consecutive_failures = 0

    def mark_provider_unhealthy(self, name: str) -> None:
        """Manually mark a provider as unhealthy.

        Args:
            name: Provider name to mark unhealthy.
        """
        status = self._status.get(name)
        if status:
            status.health = ProviderHealth.UNHEALTHY

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Route a completion request to the best available provider.

        Tries providers in order of preference, falling back to the next
        on failure. Updates health status based on results.

        Args:
            request: The LLM request.

        Returns:
            LLMResponse from whichever provider succeeded.

        Raises:
            ProviderError: If all providers fail.
        """
        candidates = self._select_provider(request)

        if not candidates:
            raise ProviderError(
                "No available providers",
                provider="router",
                retryable=False,
            )

        # Optionally compress the prompt before dispatch. This is a no-op unless
        # compression is enabled AND headroom is installed; it never raises.
        if self._compressor.active:
            compressed, stats = self._compressor.compress_messages(
                request.messages, model=request.model_override
            )
            if stats.applied:
                request = request.model_copy(update={"messages": compressed})

        last_error: Optional[Exception] = None
        for name in candidates:
            provider = self._providers[name]
            try:
                response = await provider.complete(request)
                self._update_status_success(
                    name,
                    response.latency_ms,
                    response.tokens_used,
                    response.cost_estimate,
                )
                return response
            except Exception as e:
                logger.warning(f"Provider {name} failed: {e}")
                self._update_status_failure(name, e)
                last_error = e
                continue

        # All providers failed
        raise ProviderError(
            f"All providers failed. Last error: {last_error}",
            provider="router",
            retryable=True,
        )

    async def health_check_all(self) -> Dict[str, bool]:
        """Run health checks on all registered providers.

        Returns:
            Dict mapping provider name to health check result.
        """
        results: Dict[str, bool] = {}
        for name, provider in self._providers.items():
            try:
                healthy = await provider.health_check()
                results[name] = healthy
                if healthy:
                    self.mark_provider_healthy(name)
                else:
                    self._update_status_failure(name, Exception("Health check failed"))
            except Exception:
                results[name] = False
                self._update_status_failure(name, Exception("Health check error"))
        return results

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get aggregated usage statistics across all providers.

        Returns:
            Dict with total requests, tokens, cost, and per-provider breakdown.
        """
        total_requests = 0
        total_tokens = 0
        total_cost = 0.0
        per_provider: Dict[str, Dict[str, Any]] = {}

        for name, status in self._status.items():
            total_requests += status.total_requests
            total_tokens += status.total_tokens
            total_cost += status.total_cost
            per_provider[name] = {
                "requests": status.total_requests,
                "tokens": status.total_tokens,
                "cost": status.total_cost,
                "health": status.health.value,
                "avg_latency_ms": status.avg_latency_ms,
            }

        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "providers": per_provider,
        }
