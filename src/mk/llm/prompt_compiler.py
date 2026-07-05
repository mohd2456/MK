"""Prompt compiler for efficient LLM calls.

Compiles efficient prompts: system prompt with MK personality,
compresses conversation history, injects only relevant memory,
and formats tool descriptions compactly. Goal: minimize tokens
while maximizing quality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mk.llm.models import LLMMessage, MessageRole, ToolDefinition
from mk.llm.token_manager import TokenEstimator, TokenManager


# MK system prompt - tight and focused
MK_SYSTEM_PROMPT = """You are MK, a personal AI operating system. You are direct, efficient, and capable.

Core traits:
- Quality over speed. Get it right.
- Efficient with tokens. Say what matters, skip the filler.
- Execute directly when possible. Only reason when needed.
- No hedging. Be clear and decisive.

You have access to tools for managing systems, services, and tasks. Use them when appropriate."""


class PromptCompiler:
    """Compiles efficient prompts for LLM calls.

    Responsibilities:
    - Assemble system prompt with MK personality
    - Compress old conversation history into summaries
    - Inject relevant memory snippets without bloating context
    - Format tool descriptions compactly
    - Stay within token budgets
    """

    def __init__(
        self,
        token_manager: Optional[TokenManager] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        """Initialize the prompt compiler.

        Args:
            token_manager: Token manager for budget tracking.
            system_prompt: Custom system prompt override.
        """
        self._token_manager = token_manager or TokenManager()
        self._system_prompt = system_prompt or MK_SYSTEM_PROMPT

    @property
    def system_prompt(self) -> str:
        """Return the configured system prompt."""
        return self._system_prompt

    def compile(
        self,
        messages: List[LLMMessage],
        memory_snippets: Optional[List[str]] = None,
        tools: Optional[List[ToolDefinition]] = None,
        max_tokens: Optional[int] = None,
    ) -> List[LLMMessage]:
        """Compile an efficient prompt from components.

        Assembles the full prompt within token budget:
        1. System prompt (always included)
        2. Relevant memory (injected into system context)
        3. Compressed conversation history
        4. Latest user message (always included in full)

        Args:
            messages: Conversation messages.
            memory_snippets: Relevant memory to inject.
            tools: Available tools (affects budget calculation).
            max_tokens: Maximum token budget for the compiled prompt.

        Returns:
            Compiled message list ready for LLM.
        """
        budget = max_tokens or self._token_manager._default_budget.max_input_tokens

        # Build system message with memory injection
        system_content = self._system_prompt
        if memory_snippets:
            memory_block = self._compress_memory(memory_snippets)
            system_content += f"\n\nRelevant context:\n{memory_block}"

        system_msg = LLMMessage(role=MessageRole.SYSTEM, content=system_content)
        system_tokens = TokenEstimator.estimate_tokens(system_content)

        # Reserve tokens for tools description
        tool_tokens = 0
        if tools:
            tool_tokens = self._estimate_tools_tokens(tools)

        # Available budget for conversation messages
        available = budget - system_tokens - tool_tokens - 10  # 10 token margin

        # Filter out any existing system messages (we provide our own)
        conv_messages = [m for m in messages if m.role != MessageRole.SYSTEM]

        # Truncate conversation to fit
        if available > 0:
            truncated = self._token_manager.truncate_messages(conv_messages, available)
        else:
            # At minimum keep the last message
            truncated = conv_messages[-1:] if conv_messages else []

        # Assemble final prompt
        result = [system_msg]
        result.extend(truncated)
        return result

    def _compress_memory(self, snippets: List[str]) -> str:
        """Compress memory snippets into a compact block.

        Args:
            snippets: Memory snippets to compress.

        Returns:
            Compressed memory string.
        """
        if not snippets:
            return ""
        # Deduplicate and join concisely
        seen = set()
        unique = []
        for s in snippets:
            normalized = s.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return "\n".join(f"- {s}" for s in unique)

    def _estimate_tools_tokens(self, tools: List[ToolDefinition]) -> int:
        """Estimate tokens needed for tool descriptions.

        Args:
            tools: Tool definitions.

        Returns:
            Estimated token count.
        """
        total = 0
        for tool in tools:
            # Name + description + basic parameter schema
            tool_text = f"{tool.name}: {tool.description}"
            total += TokenEstimator.estimate_tokens(tool_text)
            # Add overhead for parameter schema
            total += 20
        return total

    def compress_history(
        self, messages: List[LLMMessage], max_messages: int = 10
    ) -> List[LLMMessage]:
        """Compress old conversation history.

        Keeps the most recent messages in full and summarizes older ones.

        Args:
            messages: Full conversation history.
            max_messages: Maximum messages to keep.

        Returns:
            Compressed message list.
        """
        if len(messages) <= max_messages:
            return list(messages)

        # Keep the last max_messages messages
        recent = messages[-max_messages:]

        # Summarize what came before
        old = messages[:-max_messages]
        summary = self._summarize_messages(old)

        # Prepend summary as a system context note
        summary_msg = LLMMessage(
            role=MessageRole.SYSTEM,
            content=f"[Earlier conversation summary: {summary}]",
        )

        return [summary_msg] + recent

    def _summarize_messages(self, messages: List[LLMMessage]) -> str:
        """Create a brief summary of messages.

        This is a simple extractive summary - for production use,
        an LLM call could generate better summaries.

        Args:
            messages: Messages to summarize.

        Returns:
            Brief summary string.
        """
        if not messages:
            return "No prior context."

        # Extract key topics mentioned
        topics = []
        for msg in messages:
            # Take first sentence or first 50 chars
            content = msg.content.strip()
            if ". " in content:
                first_sentence = content.split(". ")[0] + "."
            else:
                first_sentence = content[:80]
            if first_sentence:
                topics.append(f"{msg.role.value}: {first_sentence}")

        # Keep it very compact
        if len(topics) > 5:
            topics = topics[:2] + ["..."] + topics[-2:]

        return " | ".join(topics)
