"""Shared fixtures and test doubles for wrapper tests."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from mk.core.models import AgentResponse


class FakeEngine:
    """A minimal engine double implementing the duck-typed contract.

    Configurable to simulate success, timeouts, exceptions, and specific
    output text so wrapper behavior can be tested deterministically.
    """

    def __init__(
        self,
        *,
        reply: str = "Hello from the engine.",
        tokens_used: int = 12,
        cost: float = 0.001,
        provider_used: Optional[str] = "fake-provider",
        raise_exc: Optional[BaseException] = None,
        delay: float = 0.0,
        has_llm: bool = True,
    ) -> None:
        self._reply = reply
        self._tokens = tokens_used
        self._cost = cost
        self._provider = provider_used
        self._raise = raise_exc
        self._delay = delay
        self.calls: list[str] = []
        # The wrapper inspects _agent_loop to decide llm availability.
        self._agent_loop = object() if has_llm else None

    async def process(self, user_input: str) -> AgentResponse:
        self.calls.append(user_input)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raise is not None:
            raise self._raise
        return AgentResponse(
            steps=[],
            final_response=self._reply,
            tokens_used=self._tokens,
            cost=self._cost,
            provider_used=self._provider,
        )


@pytest.fixture
def fake_engine() -> FakeEngine:
    """A healthy engine that returns a normal reply."""
    return FakeEngine()


@pytest.fixture
def make_engine():
    """Factory to build a :class:`FakeEngine` with custom behavior."""

    def _factory(**kwargs: Any) -> FakeEngine:
        return FakeEngine(**kwargs)

    return _factory
