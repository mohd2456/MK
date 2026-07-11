"""Token efficiency manager.

Estimates token counts using a simple heuristic (no heavy dependencies),
tracks budgets per conversation, manages context windows, and caches
responses to avoid redundant LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from mk.llm.models import LLMMessage, LLMResponse


class TokenEstimator:
    """Estimates token counts without heavy dependencies.

    Uses a character-based heuristic that approximates tiktoken counts.
    The approximation is: ~4 characters per token for English text,
    with adjustments for code and special characters.
    """

    # Average chars per token for different content types
    CHARS_PER_TOKEN_TEXT = 4.0
    CHARS_PER_TOKEN_CODE = 3.5
    # Overhead per message (role, formatting tokens)
    MESSAGE_OVERHEAD = 4

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Estimate token count for a text string.

        Uses a heuristic based on character count with adjustments
        for whitespace, punctuation, and code patterns.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0

        # Detect if text is likely code (has common code patterns)
        code_indicators = ["{", "}", "()", "def ", "class ", "import ", "//", "/*"]
        is_code = any(indicator in text for indicator in code_indicators)

        chars_per_token = cls.CHARS_PER_TOKEN_CODE if is_code else cls.CHARS_PER_TOKEN_TEXT

        # Count words for a more accurate base estimate
        words = text.split()
        word_count = len(words)

        # Hybrid: average of char-based and word-based estimates
        char_estimate = len(text) / chars_per_token
        word_estimate = word_count * 1.3  # ~1.3 tokens per word on average

        # Use weighted average
        estimate = char_estimate * 0.6 + word_estimate * 0.4

        return max(1, int(estimate))

    @classmethod
    def estimate_messages_tokens(cls, messages: List[LLMMessage]) -> int:
        """Estimate total tokens for a list of messages.

        Accounts for per-message overhead (role tokens, formatting).

        Args:
            messages: List of LLM messages.

        Returns:
            Estimated total token count.
        """
        total = 0
        for msg in messages:
            total += cls.estimate_tokens(msg.content)
            total += cls.MESSAGE_OVERHEAD  # role + formatting overhead
        total += 3  # Reply priming tokens
        return total


class ResponseCache:
    """LRU cache for LLM responses.

    Avoids redundant LLM calls for identical inputs. Respects
    a maximum size and TTL (time-to-live) for cache entries.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 3600.0) -> None:
        """Initialize the response cache.

        Args:
            max_size: Maximum number of cached responses.
            ttl_seconds: Time-to-live for cache entries in seconds.
        """
        self._cache: OrderedDict[str, Tuple[LLMResponse, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    def _make_key(self, messages: List[LLMMessage], **kwargs: Any) -> str:
        """Generate a cache key from messages and parameters.

        Args:
            messages: The conversation messages.
            **kwargs: Additional parameters that affect the response.

        Returns:
            Hash string as cache key.
        """
        key_data = {
            "messages": [(m.role.value, m.content) for m in messages],
            "params": {k: v for k, v in sorted(kwargs.items()) if v is not None},
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, messages: List[LLMMessage], **kwargs: Any) -> Optional[LLMResponse]:
        """Look up a cached response.

        Args:
            messages: The conversation messages.
            **kwargs: Additional parameters.

        Returns:
            Cached LLMResponse if found and not expired, None otherwise.
        """
        key = self._make_key(messages, **kwargs)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        response, timestamp = entry
        if time.time() - timestamp > self._ttl_seconds:
            # Expired
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1

        # Return a copy marked as cached
        cached_response = response.model_copy(update={"cached": True})
        return cached_response

    def put(self, messages: List[LLMMessage], response: LLMResponse, **kwargs: Any) -> None:
        """Store a response in the cache.

        Args:
            messages: The conversation messages.
            response: The LLM response to cache.
            **kwargs: Additional parameters.
        """
        key = self._make_key(messages, **kwargs)

        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (response, time.time())

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Return number of items in cache."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Return cache hit rate as a fraction."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


class TokenBudget:
    """Tracks token budget for a conversation.

    Ensures we stay within provider context window limits
    by tracking token usage and providing truncation strategies.
    """

    def __init__(self, max_tokens: int = 8000, reserve_output: int = 2000) -> None:
        """Initialize token budget.

        Args:
            max_tokens: Maximum total context window tokens.
            reserve_output: Tokens reserved for the response.
        """
        self._max_tokens = max_tokens
        self._reserve_output = reserve_output
        self._used_tokens = 0

    @property
    def max_input_tokens(self) -> int:
        """Maximum tokens available for input (total minus output reserve)."""
        return self._max_tokens - self._reserve_output

    @property
    def remaining_tokens(self) -> int:
        """Tokens remaining in the input budget."""
        return max(0, self.max_input_tokens - self._used_tokens)

    @property
    def used_tokens(self) -> int:
        """Tokens used so far."""
        return self._used_tokens

    @property
    def utilization(self) -> float:
        """Budget utilization as a fraction (0.0 to 1.0)."""
        if self.max_input_tokens == 0:
            return 1.0
        return self._used_tokens / self.max_input_tokens

    def consume(self, tokens: int) -> bool:
        """Consume tokens from the budget.

        Args:
            tokens: Number of tokens to consume.

        Returns:
            True if tokens were consumed (within budget), False if over budget.
        """
        if self._used_tokens + tokens > self.max_input_tokens:
            return False
        self._used_tokens += tokens
        return True

    def can_fit(self, tokens: int) -> bool:
        """Check if the given number of tokens fits in remaining budget.

        Args:
            tokens: Number of tokens to check.

        Returns:
            True if they fit, False otherwise.
        """
        return self._used_tokens + tokens <= self.max_input_tokens

    def reset(self) -> None:
        """Reset the budget (start fresh)."""
        self._used_tokens = 0


class TokenManager:
    """Manages token efficiency across the system.

    Combines token estimation, budget tracking, and response caching
    to minimize token usage while maintaining quality.
    """

    def __init__(
        self,
        context_window: int = 8000,
        reserve_output: int = 2000,
        cache_size: int = 100,
        cache_ttl: float = 3600.0,
    ) -> None:
        """Initialize the token manager.

        Args:
            context_window: Maximum context window tokens.
            reserve_output: Tokens reserved for output.
            cache_size: Maximum cached responses.
            cache_ttl: Cache entry TTL in seconds.
        """
        self.estimator = TokenEstimator()
        self.cache = ResponseCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self._default_budget = TokenBudget(max_tokens=context_window, reserve_output=reserve_output)
        self._budgets: Dict[str, TokenBudget] = {}

    def get_budget(self, conversation_id: str) -> TokenBudget:
        """Get or create a budget for a conversation.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            TokenBudget instance for this conversation.
        """
        if conversation_id not in self._budgets:
            self._budgets[conversation_id] = TokenBudget(
                max_tokens=self._default_budget._max_tokens,
                reserve_output=self._default_budget._reserve_output,
            )
        return self._budgets[conversation_id]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Input text.

        Returns:
            Estimated token count.
        """
        return self.estimator.estimate_tokens(text)

    def estimate_messages_tokens(self, messages: List[LLMMessage]) -> int:
        """Estimate tokens for a list of messages.

        Args:
            messages: List of messages.

        Returns:
            Estimated total tokens.
        """
        return self.estimator.estimate_messages_tokens(messages)

    def truncate_messages(self, messages: List[LLMMessage], max_tokens: int) -> List[LLMMessage]:
        """Truncate messages to fit within a token budget.

        Strategy: Keep the system message and the most recent messages.
        Drop older messages from the middle if needed.

        Args:
            messages: Full message list.
            max_tokens: Maximum tokens to fit within.

        Returns:
            Truncated message list that fits the budget.
        """
        if not messages:
            return []

        # Always keep system message (if any) and last message
        total_estimate = self.estimate_messages_tokens(messages)
        if total_estimate <= max_tokens:
            return messages

        # Separate system messages and conversation messages
        system_msgs = [m for m in messages if m.role.value == "system"]
        conv_msgs = [m for m in messages if m.role.value != "system"]

        # Start with system messages
        result = list(system_msgs)
        used = self.estimate_messages_tokens(result)

        # Add messages from the end (most recent first) until budget is full
        added_from_end: List[LLMMessage] = []
        for msg in reversed(conv_msgs):
            msg_tokens = (
                self.estimator.estimate_tokens(msg.content) + TokenEstimator.MESSAGE_OVERHEAD
            )
            if used + msg_tokens <= max_tokens:
                added_from_end.insert(0, msg)
                used += msg_tokens
            else:
                break

        result.extend(added_from_end)
        return result

    def check_cache(self, messages: List[LLMMessage], **kwargs: Any) -> Optional[LLMResponse]:
        """Check if a response is cached for these messages.

        Args:
            messages: The conversation messages.
            **kwargs: Additional request parameters.

        Returns:
            Cached response if available, None otherwise.
        """
        return self.cache.get(messages, **kwargs)

    def cache_response(
        self, messages: List[LLMMessage], response: LLMResponse, **kwargs: Any
    ) -> None:
        """Cache a response for future identical requests.

        Args:
            messages: The conversation messages.
            response: The response to cache.
            **kwargs: Additional request parameters.
        """
        self.cache.put(messages, response, **kwargs)

    def clear_conversation_budget(self, conversation_id: str) -> None:
        """Clear the budget for a conversation.

        Args:
            conversation_id: Conversation to clear.
        """
        self._budgets.pop(conversation_id, None)
