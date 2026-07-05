"""Shared test fixtures for MK tests."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from mk.config.settings import Settings
from mk.core.models import Conversation, Message, Role


@pytest.fixture
def mock_settings() -> Settings:
    """Provide a minimal Settings instance for testing."""
    return Settings(
        llm_providers=[
            {
                "name": "test-provider",
                "api_key_ref": "test_key",
                "model": "test-model",
                "endpoint": "http://localhost:8000",
                "priority": 10,
            }
        ],
        memory={
            "short_term_max_messages": 10,
            "context_window_budget": 4000,
        },
        safety={
            "max_iterations": 5,
        },
    )


@pytest.fixture
def sample_conversation() -> Conversation:
    """Provide a sample conversation with a few messages."""
    conv = Conversation()
    conv.add_message(Role.USER, "Hello MK")
    conv.add_message(Role.ASSISTANT, "Hello! How can I help you?")
    conv.add_message(Role.USER, "Check the status of my media server")
    return conv


@pytest.fixture
def mock_llm_response() -> Dict[str, Any]:
    """Provide a standard mock LLM response."""
    return {
        "content": "I'll help you with that.",
        "tokens_used": 50,
        "cost": 0.001,
        "tool_calls": [],
    }


@pytest.fixture
def mock_llm_tool_response() -> Dict[str, Any]:
    """Provide a mock LLM response with tool calls."""
    return {
        "content": "Let me check that for you.",
        "tokens_used": 75,
        "cost": 0.002,
        "tool_calls": [
            {
                "name": "check_status",
                "args": {"target": "media-server"},
            }
        ],
    }


class MockLLMProvider:
    """Mock LLM provider for testing."""

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None) -> None:
        """Initialize with a list of responses to return in order.

        Args:
            responses: List of response dicts. If None, returns a default response.
        """
        self._responses = responses or [
            {"content": "Mock response", "tokens_used": 10, "cost": 0.0, "tool_calls": []}
        ]
        self._call_count = 0
        self.calls: List[List[Dict[str, str]]] = []

    @property
    def name(self) -> str:
        """Provider name."""
        return "mock-provider"

    async def complete(
        self, messages: List[Dict[str, str]], **kwargs: Any
    ) -> Dict[str, Any]:
        """Return the next mock response.

        Args:
            messages: Input messages (recorded for assertions).
            **kwargs: Ignored.

        Returns:
            Next response from the queue.
        """
        self.calls.append(messages)
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]



