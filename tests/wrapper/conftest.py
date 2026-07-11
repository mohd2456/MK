"""Shared fixtures and fakes for wrapper tests.

These fakes stand in for a real MK engine (and thus for any real LLM call),
so the wrapper's behavior can be exercised deterministically and offline.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest


class FakeResponse:
    """Mimics the subset of ``AgentResponse`` the wrapper reads."""

    def __init__(
        self,
        final_response: str,
        provider_used: Optional[str] = None,
        tokens_used: int = 0,
        cost: float = 0.0,
        was_direct_command: bool = False,
    ) -> None:
        self.final_response = final_response
        self.provider_used = provider_used
        self.tokens_used = tokens_used
        self.cost = cost
        self.was_direct_command = was_direct_command


class FakeEngine:
    """A configurable stand-in for MKEngine/MKEngineV2.

    Configure it to return a reply, raise an exception, or sleep (to trigger
    the wrapper's timeout). Records the inputs it received for assertions.
    """

    def __init__(
        self,
        reply: str = "All good.",
        response: Any = None,
        exc: Optional[BaseException] = None,
        delay: float = 0.0,
        provider_used: Optional[str] = "openai",
        was_direct_command: bool = False,
    ) -> None:
        self._reply = reply
        self._response = response
        self._exc = exc
        self._delay = delay
        self._provider_used = provider_used
        self._was_direct = was_direct_command
        self.calls: list[str] = []

    async def process(self, user_input: str) -> Any:
        self.calls.append(user_input)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        if self._response is not None:
            return self._response
        return FakeResponse(
            final_response=self._reply,
            provider_used=self._provider_used,
            tokens_used=7,
            cost=0.0012,
            was_direct_command=self._was_direct,
        )


@pytest.fixture
def fake_engine() -> FakeEngine:
    """A healthy fake engine returning a normal reply."""
    return FakeEngine()
