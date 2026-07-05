"""Unit tests for the token manager.

Tests token counting accuracy, budget management, caching behavior,
and prompt truncation strategies.
"""

from __future__ import annotations

import time
from typing import List

import pytest

from mk.llm.models import LLMMessage, LLMResponse, MessageRole
from mk.llm.prompt_compiler import MK_SYSTEM_PROMPT, PromptCompiler
from mk.llm.token_manager import (
    ResponseCache,
    TokenBudget,
    TokenEstimator,
    TokenManager,
)


class TestTokenEstimator:
    """Tests for the token estimation heuristic."""

    def test_empty_string(self) -> None:
        """Test empty string returns 0 tokens."""
        assert TokenEstimator.estimate_tokens("") == 0

    def test_simple_text(self) -> None:
        """Test estimation for simple English text."""
        text = "Hello, how are you doing today?"
        tokens = TokenEstimator.estimate_tokens(text)
        # "Hello, how are you doing today?" is ~8 tokens in most tokenizers
        # Our heuristic should be within 10% accuracy for normal text
        assert 5 <= tokens <= 12

    def test_longer_text(self) -> None:
        """Test estimation for longer text."""
        text = "The quick brown fox jumps over the lazy dog. " * 10
        tokens = TokenEstimator.estimate_tokens(text)
        # ~10 tokens per sentence, 10 sentences = ~100 tokens
        assert 70 <= tokens <= 140

    def test_code_text(self) -> None:
        """Test estimation for code (slightly different ratio)."""
        code = "def hello_world():\n    print('Hello, World!')\n    return True"
        tokens = TokenEstimator.estimate_tokens(code)
        # Code tends to have more tokens per character
        assert tokens > 0
        assert 10 <= tokens <= 30

    def test_single_word(self) -> None:
        """Test single word."""
        assert TokenEstimator.estimate_tokens("hello") >= 1

    def test_message_overhead(self) -> None:
        """Test that message estimation includes overhead."""
        messages = [
            LLMMessage(role=MessageRole.USER, content="Hello"),
        ]
        tokens = TokenEstimator.estimate_messages_tokens(messages)
        # Should be more than just the text (includes role overhead + reply priming)
        text_only = TokenEstimator.estimate_tokens("Hello")
        assert tokens > text_only

    def test_multiple_messages(self) -> None:
        """Test token estimation for multiple messages."""
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
            LLMMessage(role=MessageRole.USER, content="What is 2+2?"),
            LLMMessage(role=MessageRole.ASSISTANT, content="4"),
        ]
        tokens = TokenEstimator.estimate_messages_tokens(messages)
        # Should account for all messages + overhead
        assert tokens > 10

    def test_accuracy_within_bounds(self) -> None:
        """Test that estimates are reasonable for typical content."""
        # A typical paragraph - most tokenizers give ~50-70 tokens
        text = (
            "Machine learning is a subset of artificial intelligence "
            "that focuses on building systems that can learn from and make "
            "decisions based on data. It encompasses various algorithms "
            "and statistical models that enable computers to perform tasks "
            "without explicit programming."
        )
        tokens = TokenEstimator.estimate_tokens(text)
        # Accept a wide range since this is a heuristic
        assert 30 <= tokens <= 80


class TestResponseCache:
    """Tests for the response cache."""

    def _make_messages(self, content: str = "test") -> List[LLMMessage]:
        return [LLMMessage(role=MessageRole.USER, content=content)]

    def _make_response(self, content: str = "cached") -> LLMResponse:
        return LLMResponse(
            content=content,
            tokens_used=10,
            provider_used="test",
            model_used="test-model",
        )

    def test_cache_miss(self) -> None:
        """Test cache miss returns None."""
        cache = ResponseCache()
        result = cache.get(self._make_messages("hello"))
        assert result is None

    def test_cache_hit(self) -> None:
        """Test storing and retrieving from cache."""
        cache = ResponseCache()
        messages = self._make_messages("hello")
        response = self._make_response("world")

        cache.put(messages, response)
        result = cache.get(messages)

        assert result is not None
        assert result.content == "world"
        assert result.cached is True

    def test_cache_different_messages(self) -> None:
        """Test that different messages have different cache entries."""
        cache = ResponseCache()
        msg1 = self._make_messages("hello")
        msg2 = self._make_messages("goodbye")

        cache.put(msg1, self._make_response("reply-1"))
        cache.put(msg2, self._make_response("reply-2"))

        r1 = cache.get(msg1)
        r2 = cache.get(msg2)

        assert r1 is not None
        assert r1.content == "reply-1"
        assert r2 is not None
        assert r2.content == "reply-2"

    def test_cache_expiry(self) -> None:
        """Test that expired entries are not returned."""
        cache = ResponseCache(ttl_seconds=0.01)
        messages = self._make_messages("test")
        cache.put(messages, self._make_response())

        # Wait for expiry
        time.sleep(0.02)

        result = cache.get(messages)
        assert result is None

    def test_cache_max_size(self) -> None:
        """Test that cache evicts oldest entries at capacity."""
        cache = ResponseCache(max_size=2)

        cache.put(self._make_messages("one"), self._make_response("r1"))
        cache.put(self._make_messages("two"), self._make_response("r2"))
        cache.put(self._make_messages("three"), self._make_response("r3"))

        # Oldest (one) should be evicted
        assert cache.get(self._make_messages("one")) is None
        assert cache.get(self._make_messages("two")) is not None
        assert cache.get(self._make_messages("three")) is not None

    def test_cache_clear(self) -> None:
        """Test clearing the cache."""
        cache = ResponseCache()
        cache.put(self._make_messages("test"), self._make_response())
        assert cache.size == 1

        cache.clear()
        assert cache.size == 0

    def test_cache_hit_rate(self) -> None:
        """Test hit rate calculation."""
        cache = ResponseCache()
        messages = self._make_messages("test")
        cache.put(messages, self._make_response())

        cache.get(messages)  # hit
        cache.get(messages)  # hit
        cache.get(self._make_messages("miss"))  # miss

        assert cache.hit_rate == 2.0 / 3.0

    def test_cache_stats(self) -> None:
        """Test cache statistics."""
        cache = ResponseCache(max_size=50)
        cache.put(self._make_messages("a"), self._make_response())
        cache.put(self._make_messages("b"), self._make_response())

        stats = cache.stats
        assert stats["size"] == 2
        assert stats["max_size"] == 50

    def test_cache_with_kwargs(self) -> None:
        """Test that kwargs differentiate cache entries."""
        cache = ResponseCache()
        messages = self._make_messages("test")

        cache.put(messages, self._make_response("temp-0.5"), temperature=0.5)
        cache.put(messages, self._make_response("temp-1.0"), temperature=1.0)

        r1 = cache.get(messages, temperature=0.5)
        r2 = cache.get(messages, temperature=1.0)

        assert r1 is not None
        assert r1.content == "temp-0.5"
        assert r2 is not None
        assert r2.content == "temp-1.0"


class TestTokenBudget:
    """Tests for the token budget tracker."""

    def test_initial_budget(self) -> None:
        """Test initial budget values."""
        budget = TokenBudget(max_tokens=8000, reserve_output=2000)
        assert budget.max_input_tokens == 6000
        assert budget.remaining_tokens == 6000
        assert budget.used_tokens == 0
        assert budget.utilization == 0.0

    def test_consume_tokens(self) -> None:
        """Test consuming tokens from budget."""
        budget = TokenBudget(max_tokens=1000, reserve_output=200)
        assert budget.consume(500) is True
        assert budget.used_tokens == 500
        assert budget.remaining_tokens == 300

    def test_consume_over_budget(self) -> None:
        """Test that consuming over budget returns False."""
        budget = TokenBudget(max_tokens=1000, reserve_output=200)
        # max_input = 800
        assert budget.consume(900) is False
        assert budget.used_tokens == 0  # Not consumed

    def test_can_fit(self) -> None:
        """Test checking if tokens fit."""
        budget = TokenBudget(max_tokens=1000, reserve_output=200)
        assert budget.can_fit(800) is True
        assert budget.can_fit(801) is False

    def test_reset(self) -> None:
        """Test resetting the budget."""
        budget = TokenBudget(max_tokens=1000, reserve_output=200)
        budget.consume(500)
        budget.reset()
        assert budget.used_tokens == 0
        assert budget.remaining_tokens == 800

    def test_utilization(self) -> None:
        """Test utilization calculation."""
        budget = TokenBudget(max_tokens=1000, reserve_output=0)
        budget.consume(500)
        assert budget.utilization == 0.5


class TestTokenManager:
    """Tests for the TokenManager (combined functionality)."""

    def test_estimate_tokens(self) -> None:
        """Test token estimation via manager."""
        manager = TokenManager()
        tokens = manager.estimate_tokens("Hello world")
        assert tokens > 0

    def test_get_budget(self) -> None:
        """Test getting/creating conversation budgets."""
        manager = TokenManager(context_window=4000, reserve_output=1000)
        budget = manager.get_budget("conv-1")
        assert budget.max_input_tokens == 3000

        # Same budget returned for same ID
        budget2 = manager.get_budget("conv-1")
        assert budget2 is budget

    def test_cache_integration(self) -> None:
        """Test cache through the manager."""
        manager = TokenManager()
        messages = [LLMMessage(role=MessageRole.USER, content="hello")]
        response = LLMResponse(
            content="hi", tokens_used=5, provider_used="test", model_used="m"
        )

        assert manager.check_cache(messages) is None
        manager.cache_response(messages, response)
        cached = manager.check_cache(messages)
        assert cached is not None
        assert cached.content == "hi"
        assert cached.cached is True

    def test_truncate_messages_within_budget(self) -> None:
        """Test that messages within budget are not truncated."""
        manager = TokenManager()
        messages = [
            LLMMessage(role=MessageRole.USER, content="short message"),
        ]
        result = manager.truncate_messages(messages, 1000)
        assert len(result) == 1

    def test_truncate_messages_over_budget(self) -> None:
        """Test truncation of messages exceeding budget."""
        manager = TokenManager()
        messages = [
            LLMMessage(role=MessageRole.USER, content="message " * 50),
            LLMMessage(role=MessageRole.ASSISTANT, content="reply " * 50),
            LLMMessage(role=MessageRole.USER, content="follow up " * 50),
            LLMMessage(role=MessageRole.ASSISTANT, content="another " * 50),
            LLMMessage(role=MessageRole.USER, content="latest question"),
        ]
        # Very small budget - should keep most recent
        result = manager.truncate_messages(messages, 50)
        assert len(result) < len(messages)
        # Latest message should always be included
        assert result[-1].content == "latest question"

    def test_truncate_preserves_system_message(self) -> None:
        """Test that system messages are preserved during truncation."""
        manager = TokenManager()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are MK."),
            LLMMessage(role=MessageRole.USER, content="long " * 100),
            LLMMessage(role=MessageRole.USER, content="latest"),
        ]
        result = manager.truncate_messages(messages, 50)
        # System message should be preserved
        system_msgs = [m for m in result if m.role == MessageRole.SYSTEM]
        assert len(system_msgs) == 1

    def test_clear_conversation_budget(self) -> None:
        """Test clearing a conversation's budget."""
        manager = TokenManager()
        budget = manager.get_budget("conv-1")
        budget.consume(100)

        manager.clear_conversation_budget("conv-1")
        new_budget = manager.get_budget("conv-1")
        assert new_budget.used_tokens == 0


class TestPromptCompiler:
    """Tests for the prompt compiler."""

    def test_compile_basic(self) -> None:
        """Test basic prompt compilation."""
        compiler = PromptCompiler()
        messages = [
            LLMMessage(role=MessageRole.USER, content="Hello MK"),
        ]
        result = compiler.compile(messages)

        # Should have system message + user message
        assert len(result) == 2
        assert result[0].role == MessageRole.SYSTEM
        assert "MK" in result[0].content
        assert result[1].content == "Hello MK"

    def test_compile_with_memory(self) -> None:
        """Test compilation with memory snippets."""
        compiler = PromptCompiler()
        messages = [
            LLMMessage(role=MessageRole.USER, content="Check plex"),
        ]
        memory = ["User prefers Plex over Jellyfin", "Media server is at 192.168.1.100"]

        result = compiler.compile(messages, memory_snippets=memory)
        system_content = result[0].content
        assert "Relevant context:" in system_content
        assert "Plex" in system_content

    def test_compile_respects_budget(self) -> None:
        """Test that compilation respects token budget."""
        compiler = PromptCompiler()
        # Create many messages that exceed budget
        messages = [
            LLMMessage(role=MessageRole.USER, content="question " * 100)
            for _ in range(20)
        ]

        result = compiler.compile(messages, max_tokens=200)
        # Should be fewer messages than input
        assert len(result) < 21  # 20 msgs + system

    def test_compile_removes_existing_system(self) -> None:
        """Test that existing system messages are replaced with MK's."""
        compiler = PromptCompiler()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="Old system prompt"),
            LLMMessage(role=MessageRole.USER, content="Hello"),
        ]
        result = compiler.compile(messages)

        # Only one system message (MK's)
        system_msgs = [m for m in result if m.role == MessageRole.SYSTEM]
        assert len(system_msgs) == 1
        assert "MK" in system_msgs[0].content
        assert "Old system prompt" not in system_msgs[0].content

    def test_compile_with_tools(self) -> None:
        """Test that tool definitions affect budget calculation."""
        from mk.llm.models import ToolDefinition

        compiler = PromptCompiler()
        messages = [
            LLMMessage(role=MessageRole.USER, content="Do something"),
        ]
        tools = [
            ToolDefinition(
                name="long_tool",
                description="A tool with a very long description " * 20,
                parameters={"type": "object"},
            )
        ]

        # Should still compile without error
        result = compiler.compile(messages, tools=tools, max_tokens=500)
        assert len(result) >= 2  # system + at least one msg

    def test_compress_history(self) -> None:
        """Test conversation history compression."""
        compiler = PromptCompiler()
        messages = [
            LLMMessage(role=MessageRole.USER, content=f"Message {i}")
            for i in range(20)
        ]

        result = compiler.compress_history(messages, max_messages=5)
        # Should have a summary + 5 recent messages
        assert len(result) <= 6
        # Last message should be preserved
        assert result[-1].content == "Message 19"

    def test_compress_history_short(self) -> None:
        """Test that short history is not compressed."""
        compiler = PromptCompiler()
        messages = [
            LLMMessage(role=MessageRole.USER, content="Hello"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Hi"),
        ]

        result = compiler.compress_history(messages, max_messages=10)
        assert len(result) == 2

    def test_system_prompt_content(self) -> None:
        """Test that system prompt has MK personality."""
        compiler = PromptCompiler()
        assert "MK" in compiler.system_prompt
        assert "Quality over speed" in compiler.system_prompt

    def test_custom_system_prompt(self) -> None:
        """Test custom system prompt override."""
        compiler = PromptCompiler(system_prompt="Custom prompt")
        assert compiler.system_prompt == "Custom prompt"

    def test_memory_deduplication(self) -> None:
        """Test that duplicate memory snippets are removed."""
        compiler = PromptCompiler()
        messages = [LLMMessage(role=MessageRole.USER, content="test")]
        memory = ["fact one", "fact one", "fact two", "fact two"]

        result = compiler.compile(messages, memory_snippets=memory)
        system_content = result[0].content
        # Should only appear once each
        assert system_content.count("fact one") == 1
        assert system_content.count("fact two") == 1
