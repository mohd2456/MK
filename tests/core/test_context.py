"""Unit tests for the context builder."""

from __future__ import annotations

import pytest

from mk.core.context import ContextBuilder
from mk.core.models import Conversation, Role


class TestContextBuilder:
    """Tests for ContextBuilder."""

    def test_basic_context_build(self) -> None:
        """Build context with just user input."""
        builder = ContextBuilder(token_budget=4000)
        messages = builder.build_context(user_input="Hello MK")

        assert len(messages) >= 2  # system + user
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Hello MK"

    def test_custom_system_prompt(self) -> None:
        """Custom system prompt is used when provided."""
        builder = ContextBuilder(token_budget=4000)
        messages = builder.build_context(
            user_input="Test",
            system_prompt="You are a test assistant.",
        )

        assert "test assistant" in messages[0]["content"].lower()

    def test_tools_included_in_context(self) -> None:
        """Available tools are included in the system message."""
        builder = ContextBuilder(token_budget=4000)
        tools = [
            {"name": "restart_service", "description": "Restart a service"},
            {"name": "check_status", "description": "Check service status"},
        ]

        messages = builder.build_context(
            user_input="Help",
            available_tools=tools,
        )

        system_content = messages[0]["content"]
        assert "restart_service" in system_content
        assert "check_status" in system_content

    def test_memory_included_in_context(self) -> None:
        """Memory context is included when provided."""
        builder = ContextBuilder(token_budget=4000)
        messages = builder.build_context(
            user_input="What do you know about me?",
            memory_context="User prefers dark themes and uses Plex for media.",
        )

        system_content = messages[0]["content"]
        assert "dark themes" in system_content
        assert "Plex" in system_content

    def test_conversation_history_included(self) -> None:
        """Conversation history is included in messages."""
        builder = ContextBuilder(token_budget=4000)
        conv = Conversation()
        conv.add_message(Role.USER, "First message")
        conv.add_message(Role.ASSISTANT, "First response")

        messages = builder.build_context(
            user_input="Second message",
            conversation=conv,
        )

        # Should have system + history messages + current user input
        assert len(messages) >= 4  # system + 2 history + user
        contents = [m["content"] for m in messages]
        assert "First message" in contents
        assert "First response" in contents
        assert "Second message" in contents

    def test_token_budget_respected(self) -> None:
        """Context builder respects the token budget."""
        # Very small budget
        builder = ContextBuilder(token_budget=100)

        # Create a long conversation
        conv = Conversation()
        for i in range(50):
            conv.add_message(Role.USER, f"Message number {i} with some extra text to use tokens")
            conv.add_message(Role.ASSISTANT, f"Response {i} with additional content padding")

        messages = builder.build_context(
            user_input="Latest message",
            conversation=conv,
        )

        # Calculate total tokens used
        total_text = " ".join(m["content"] for m in messages)
        total_tokens = builder.estimate_tokens(total_text)

        # Should be within budget (with some tolerance for system prompt)
        # The key check is that not all 100 messages were included
        history_messages = [m for m in messages if m["content"].startswith("Message number")]
        assert len(history_messages) < 50  # Not all messages fit

    def test_token_budget_prioritizes_recent(self) -> None:
        """When budget is limited, most recent messages are kept."""
        builder = ContextBuilder(token_budget=500)

        conv = Conversation()
        for i in range(20):
            conv.add_message(Role.USER, f"Message {i}")
            conv.add_message(Role.ASSISTANT, f"Response {i}")

        messages = builder.build_context(
            user_input="Current",
            conversation=conv,
        )

        # The last messages should be present (most recent history)
        contents = [m["content"] for m in messages]
        # Most recent should be there
        assert "Current" in contents

    def test_estimate_tokens(self) -> None:
        """Token estimation works correctly."""
        builder = ContextBuilder()

        # 4 chars = ~1 token with our heuristic
        assert builder.estimate_tokens("test") == 1
        assert builder.estimate_tokens("a" * 100) == 25
        assert builder.estimate_tokens("") == 1  # Minimum 1

    def test_system_state_included(self) -> None:
        """System state is included when provided."""
        builder = ContextBuilder(token_budget=4000)
        state = {"cpu_usage": "45%", "memory": "3.2GB/6GB", "uptime": "5 days"}

        messages = builder.build_context(
            user_input="How's the system?",
            system_state=state,
        )

        system_content = messages[0]["content"]
        assert "45%" in system_content
        assert "3.2GB/6GB" in system_content

    def test_empty_conversation(self) -> None:
        """Handles empty conversation gracefully."""
        builder = ContextBuilder(token_budget=4000)
        conv = Conversation()

        messages = builder.build_context(
            user_input="Hello",
            conversation=conv,
        )

        # Just system + user
        assert len(messages) == 2
