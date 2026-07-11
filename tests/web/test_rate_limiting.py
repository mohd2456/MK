"""Integration tests for rate limiting middleware."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from mk.web.app import RateLimiter


def test_rate_limiter_allows_requests():
    """Test rate limiter allows requests within limit."""
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert limiter.is_allowed("192.168.1.1") is True


def test_rate_limiter_blocks_excess():
    """Test rate limiter blocks requests exceeding limit."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        assert limiter.is_allowed("192.168.1.1") is True
    # 4th request should be blocked
    assert limiter.is_allowed("192.168.1.1") is False


def test_rate_limiter_per_ip():
    """Test rate limiter tracks IPs independently."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("192.168.1.1") is True
    assert limiter.is_allowed("192.168.1.1") is True
    assert limiter.is_allowed("192.168.1.1") is False
    # Different IP should still be allowed
    assert limiter.is_allowed("192.168.1.2") is True


def test_rate_limiter_remaining():
    """Test remaining count."""
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    assert limiter.remaining("192.168.1.1") == 5
    limiter.is_allowed("192.168.1.1")
    assert limiter.remaining("192.168.1.1") == 4


@pytest.mark.asyncio
async def test_rate_limit_middleware_passes(auth_client: AsyncClient):
    """Test that normal requests pass through rate limiter."""
    # A few requests should work fine
    for _ in range(5):
        response = await auth_client.get("/api/v1/system/health")
        assert response.status_code == 200
