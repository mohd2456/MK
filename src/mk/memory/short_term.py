"""Short-term conversation memory.

Stores the current conversation turns with a sliding window.
When the conversation exceeds the configured threshold, older
turns are compressed into summaries to save token budget.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from mk.clock import utcnow
from mk.memory.models import ConversationTurn


def _estimate_tokens(text: str) -> int:
    """Estimate token count for a piece of text.

    Uses a simple heuristic of ~4 characters per token.
    This is a rough approximation suitable for budget management.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // 4)


class ShortTermMemory:
    """Short-term conversation memory with sliding window.

    Maintains a list of conversation turns, automatically
    summarizing older turns when the conversation exceeds
    the configured threshold. Provides methods to retrieve
    recent context within a token budget.
    """

    def __init__(
        self,
        max_messages: int = 50,
        summary_threshold: int = 20,
    ) -> None:
        """Initialize short-term memory.

        Args:
            max_messages: Maximum number of turns to store before eviction.
            summary_threshold: Number of messages that triggers summarization
                of older turns.
        """
        self._turns: List[ConversationTurn] = []
        self._max_messages = max_messages
        self._summary_threshold = summary_threshold
        self._summaries: List[str] = []

    @property
    def turns(self) -> List[ConversationTurn]:
        """Return all conversation turns."""
        return list(self._turns)

    @property
    def turn_count(self) -> int:
        """Return the number of turns in memory."""
        return len(self._turns)

    @property
    def summaries(self) -> List[str]:
        """Return all compressed summaries of older conversations."""
        return list(self._summaries)

    def add_turn(self, role: str, content: str, timestamp: Optional[datetime] = None) -> None:
        """Add a new conversation turn.

        If the turn count exceeds the max, triggers summarization
        of the oldest turns.

        Args:
            role: The message role (user, assistant, system).
            content: The message content.
            timestamp: Optional timestamp (defaults to now).
        """
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=timestamp or utcnow(),
            token_count=_estimate_tokens(content),
        )
        self._turns.append(turn)

        if len(self._turns) > self._max_messages:
            self._compress_oldest()

    def recent_context(self, n_tokens: int) -> List[ConversationTurn]:
        """Return as many recent turns as fit within the token budget.

        Starts from the most recent turn and works backward,
        including turns until the token budget is exhausted.

        Args:
            n_tokens: Maximum number of tokens for the context.

        Returns:
            List of conversation turns that fit within the budget,
            ordered from oldest to newest.
        """
        result: List[ConversationTurn] = []
        budget_remaining = n_tokens

        # First, reserve space for summaries if they exist
        summary_tokens = 0
        if self._summaries:
            summary_text = " ".join(self._summaries)
            summary_tokens = _estimate_tokens(summary_text)
            budget_remaining -= summary_tokens

        # Walk backward through turns
        for turn in reversed(self._turns):
            turn_tokens = turn.token_count
            if turn_tokens <= budget_remaining:
                result.insert(0, turn)
                budget_remaining -= turn_tokens
            else:
                break

        return result

    def get_context_with_summaries(self, n_tokens: int) -> dict:
        """Return context including both summaries and recent turns.

        Args:
            n_tokens: Maximum total token budget.

        Returns:
            Dictionary with 'summaries' and 'recent_turns' keys.
        """
        summary_text = ""
        budget = n_tokens

        if self._summaries:
            summary_text = " ".join(self._summaries)
            summary_tokens = _estimate_tokens(summary_text)
            budget -= summary_tokens

        recent = self.recent_context(budget)

        return {
            "summaries": summary_text,
            "recent_turns": recent,
        }

    def _compress_oldest(self) -> None:
        """Compress the oldest turns into a summary.

        Takes the oldest batch of turns (up to summary_threshold)
        and creates a compressed summary, removing those turns
        from active memory.
        """
        if len(self._turns) <= self._summary_threshold:
            return

        # Take the oldest turns to summarize
        n_to_compress = len(self._turns) - self._summary_threshold
        to_compress = self._turns[:n_to_compress]
        self._turns = self._turns[n_to_compress:]

        # Create a simple summary (in production, this would call an LLM)
        summary_parts = []
        for turn in to_compress:
            # Use the summary if available, otherwise truncate content
            text = turn.summary or turn.content[:100]
            summary_parts.append(f"{turn.role}: {text}")

        summary = "[Previous conversation] " + " | ".join(summary_parts)
        self._summaries.append(summary)

    def clear(self) -> None:
        """Clear all conversation memory."""
        self._turns.clear()
        self._summaries.clear()

    def needs_summarization(self) -> bool:
        """Check if the conversation has grown enough to need summarization.

        Returns:
            True if turn count exceeds the summary threshold.
        """
        return len(self._turns) >= self._summary_threshold
