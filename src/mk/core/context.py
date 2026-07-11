"""Context builder for MK.

Assembles the prompt context by combining user input with relevant memory,
system state, and available tools. Implements token budget management
to keep context compact and cost-efficient.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mk.core.models import Conversation, Message


class ContextBuilder:
    """Builds enriched context for LLM calls.

    Takes user input and enriches it with conversation history,
    relevant memory, system state, and available tool descriptions.
    Respects a token budget to keep prompts tight and costs low.
    """

    # Approximate characters per token (conservative estimate)
    CHARS_PER_TOKEN = 4

    def __init__(self, token_budget: int = 8000) -> None:
        """Initialize the context builder.

        Args:
            token_budget: Maximum tokens allowed for the assembled context.
        """
        self.token_budget = token_budget

    def estimate_tokens(self, text: str) -> int:
        """Estimate the token count for a piece of text.

        Uses a simple character-based heuristic. A more accurate
        tokenizer can be plugged in later.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated number of tokens.
        """
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def build_context(
        self,
        user_input: str,
        conversation: Optional[Conversation] = None,
        memory_context: Optional[str] = None,
        system_state: Optional[Dict[str, Any]] = None,
        available_tools: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build the full context for an LLM call.

        Assembles all context components within the token budget.
        Priority order (highest first):
        1. System prompt
        2. User input (always included)
        3. Available tools
        4. Memory context
        5. Conversation history (most recent first)
        6. System state

        Args:
            user_input: The current user input.
            conversation: Current conversation history.
            memory_context: Relevant long-term memory summary.
            system_state: Current system state information.
            available_tools: List of available tool descriptions.
            system_prompt: The system prompt defining MK's behavior.

        Returns:
            List of message dicts ready for LLM consumption.
        """
        messages: List[Dict[str, str]] = []
        used_tokens = 0

        # 1. System prompt (always included if provided)
        if system_prompt:
            sys_content = system_prompt
        else:
            sys_content = self._default_system_prompt()

        # Add tools to system prompt if available
        if available_tools:
            tools_text = self._format_tools(available_tools)
            sys_content += f"\n\n{tools_text}"

        # Add memory to system prompt if available
        if memory_context:
            memory_tokens = self.estimate_tokens(memory_context)
            if used_tokens + memory_tokens + self.estimate_tokens(sys_content) < self.token_budget:
                sys_content += f"\n\n## What you remember about the user:\n{memory_context}"

        # Add system state if available
        if system_state:
            state_text = self._format_system_state(system_state)
            state_tokens = self.estimate_tokens(state_text)
            if used_tokens + state_tokens + self.estimate_tokens(sys_content) < self.token_budget:
                sys_content += f"\n\n## Current system state:\n{state_text}"

        messages.append({"role": "system", "content": sys_content})
        used_tokens += self.estimate_tokens(sys_content)

        # 2. Conversation history (fit as much recent history as possible)
        if conversation and conversation.messages:
            history_messages = self._fit_conversation_history(
                conversation.messages,
                self.token_budget - used_tokens - self.estimate_tokens(user_input) - 50,
            )
            for msg in history_messages:
                messages.append({"role": msg.role.value, "content": msg.content})
                used_tokens += self.estimate_tokens(msg.content)

        # 3. Current user input (always included)
        messages.append({"role": "user", "content": user_input})
        used_tokens += self.estimate_tokens(user_input)

        return messages

    @property
    def remaining_budget(self) -> int:
        """Return the current token budget."""
        return self.token_budget

    def _default_system_prompt(self) -> str:
        """Return the default MK system prompt."""
        return (
            "You are MK, a personal AI operating system. "
            "You are loyal to your user and only your user. "
            "You orchestrate their homelab, manage services, execute tasks, "
            "and handle anything they ask. You are direct, efficient, and smart. "
            "You remember everything about your user and get better over time.\n\n"
            "Rules:\n"
            "- Be concise. No fluff.\n"
            "- If a task needs tools, use them.\n"
            "- If you need to think, think. Quality over speed.\n"
            "- If something is dangerous, ask for confirmation.\n"
            "- Never make up information. If unsure, say so."
        )

    def _format_tools(self, tools: List[Dict[str, str]]) -> str:
        """Format available tools for the system prompt.

        Args:
            tools: List of tool descriptions.

        Returns:
            Formatted tools section.
        """
        lines = ["## Available tools:"]
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            lines.append(f"- **{name}**: {desc}")
        return "\n".join(lines)

    def _format_system_state(self, state: Dict[str, Any]) -> str:
        """Format system state for inclusion in context.

        Args:
            state: System state dictionary.

        Returns:
            Formatted state string.
        """
        lines = []
        for key, value in state.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def _fit_conversation_history(self, messages: List[Message], budget: int) -> List[Message]:
        """Select conversation messages that fit within the token budget.

        Prioritizes most recent messages. Walks backward from the end
        and includes as many messages as fit.

        Args:
            messages: All conversation messages.
            budget: Available token budget for history.

        Returns:
            List of messages that fit within budget (in chronological order).
        """
        if budget <= 0:
            return []

        selected: List[Message] = []
        used = 0

        # Walk backward from most recent
        for msg in reversed(messages):
            msg_tokens = self.estimate_tokens(msg.content)
            if used + msg_tokens > budget:
                break
            selected.append(msg)
            used += msg_tokens

        # Return in chronological order
        selected.reverse()
        return selected
