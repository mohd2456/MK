"""Tests for short-term conversation memory."""

from __future__ import annotations

import pytest

from mk.memory.short_term import ShortTermMemory, _estimate_tokens


class TestEstimateTokens:
    """Tests for the token estimation function."""

    def test_empty_string(self) -> None:
        """Empty string should return 1 (minimum)."""
        assert _estimate_tokens("") == 1

    def test_short_string(self) -> None:
        """Short string token estimate."""
        assert _estimate_tokens("hello") == 1

    def test_longer_string(self) -> None:
        """Longer string gives proportional estimate."""
        text = "This is a longer test string for token estimation"
        tokens = _estimate_tokens(text)
        assert tokens > 5
        assert tokens < 20


class TestShortTermMemory:
    """Tests for the ShortTermMemory class."""

    def test_init_defaults(self) -> None:
        """Default initialization with standard values."""
        mem = ShortTermMemory()
        assert mem.turn_count == 0
        assert mem.turns == []
        assert mem.summaries == []

    def test_add_turn(self) -> None:
        """Adding a turn stores it correctly."""
        mem = ShortTermMemory()
        mem.add_turn("user", "Hello MK")
        assert mem.turn_count == 1
        assert mem.turns[0].role == "user"
        assert mem.turns[0].content == "Hello MK"

    def test_add_multiple_turns(self) -> None:
        """Multiple turns are stored in order."""
        mem = ShortTermMemory()
        mem.add_turn("user", "First message")
        mem.add_turn("assistant", "Response")
        mem.add_turn("user", "Second message")
        assert mem.turn_count == 3
        assert mem.turns[0].content == "First message"
        assert mem.turns[2].content == "Second message"

    def test_token_count_stored(self) -> None:
        """Each turn stores its token count."""
        mem = ShortTermMemory()
        mem.add_turn("user", "Hello world this is a test")
        assert mem.turns[0].token_count > 0

    def test_sliding_window_triggers(self) -> None:
        """Exceeding max_messages triggers compression."""
        mem = ShortTermMemory(max_messages=5, summary_threshold=3)
        for i in range(7):
            mem.add_turn("user", f"Message {i}")

        # Should have compressed some messages
        assert mem.turn_count <= 5
        assert len(mem.summaries) > 0

    def test_recent_context_respects_budget(self) -> None:
        """recent_context returns turns within token budget."""
        mem = ShortTermMemory()
        # Add turns with known sizes
        for i in range(10):
            mem.add_turn("user", f"Message number {i} with some content here")

        # Small budget should return fewer turns
        small_context = mem.recent_context(n_tokens=20)
        large_context = mem.recent_context(n_tokens=2000)

        assert len(small_context) <= len(large_context)
        assert len(large_context) == 10  # All should fit in 2000 tokens

    def test_recent_context_newest_first_priority(self) -> None:
        """Recent context prioritizes newest messages."""
        mem = ShortTermMemory()
        mem.add_turn("user", "Old message")
        mem.add_turn("assistant", "Old response")
        mem.add_turn("user", "New message")

        # Very tight budget - should still include newest
        context = mem.recent_context(n_tokens=10)
        if context:
            # The last entry should be the newest that fits
            assert context[-1].content == "New message"

    def test_get_context_with_summaries(self) -> None:
        """get_context_with_summaries returns both summaries and turns."""
        mem = ShortTermMemory(max_messages=5, summary_threshold=3)
        for i in range(7):
            mem.add_turn("user", f"Message {i}")

        result = mem.get_context_with_summaries(n_tokens=5000)
        assert "summaries" in result
        assert "recent_turns" in result

    def test_needs_summarization(self) -> None:
        """needs_summarization returns true at threshold."""
        mem = ShortTermMemory(summary_threshold=5)
        for i in range(4):
            mem.add_turn("user", f"Message {i}")
        assert not mem.needs_summarization()

        mem.add_turn("user", "Message 4")
        assert mem.needs_summarization()

    def test_clear(self) -> None:
        """Clear removes all turns and summaries."""
        mem = ShortTermMemory()
        mem.add_turn("user", "Hello")
        mem.add_turn("assistant", "Hi")
        mem.clear()
        assert mem.turn_count == 0
        assert mem.summaries == []

    def test_summarization_preserves_recent(self) -> None:
        """After summarization, recent messages are kept intact."""
        mem = ShortTermMemory(max_messages=5, summary_threshold=3)
        for i in range(6):
            mem.add_turn("user", f"Message {i}")

        # Most recent messages should still be accessible
        assert any("Message 5" in t.content for t in mem.turns)
