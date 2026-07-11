"""Memory manager coordinating all three memory tiers.

Provides a unified interface for querying relevant memories
across short-term conversation, long-term user knowledge,
and system state tiers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mk.memory.long_term import LongTermMemory
from mk.memory.models import MemoryCategory, MemoryEntry
from mk.memory.short_term import ShortTermMemory, _estimate_tokens
from mk.memory.system_state import SystemStateMemory


class MemoryManager:
    """Unified memory manager coordinating all three tiers.

    Provides smart retrieval: given a user query, returns the
    most relevant memories from all tiers within a token budget.
    Used by the context builder to enrich LLM prompts with
    relevant memories.
    """

    def __init__(
        self,
        short_term: Optional[ShortTermMemory] = None,
        long_term: Optional[LongTermMemory] = None,
        system_state: Optional[SystemStateMemory] = None,
        context_budget: int = 8000,
    ) -> None:
        """Initialize the memory manager.

        Args:
            short_term: Short-term memory instance. Creates default if None.
            long_term: Long-term memory instance. Creates default if None.
            system_state: System state instance. Creates default if None.
            context_budget: Default token budget for context retrieval.
        """
        self.short_term = short_term or ShortTermMemory()
        self.long_term = long_term or LongTermMemory()
        self.system_state = system_state or SystemStateMemory()
        self._context_budget = context_budget

    @property
    def context_budget(self) -> int:
        """Return the configured context token budget."""
        return self._context_budget

    def retrieve_context(
        self,
        query: str,
        token_budget: Optional[int] = None,
    ) -> List[MemoryEntry]:
        """Retrieve the most relevant memories for a query.

        Queries all three memory tiers and returns a combined,
        ranked list of relevant memories within the token budget.
        Budget allocation:
        - 50% for conversation context (short-term)
        - 30% for user knowledge (long-term)
        - 20% for system state

        Args:
            query: The user query to find relevant memories for.
            token_budget: Maximum tokens for the result.
                Uses the default context_budget if None.

        Returns:
            List of MemoryEntry objects ranked by relevance.
        """
        budget = token_budget or self._context_budget
        entries: List[MemoryEntry] = []

        # Allocate budget across tiers
        conversation_budget = int(budget * 0.5)
        knowledge_budget = int(budget * 0.3)
        state_budget = int(budget * 0.2)

        # Short-term: recent conversation
        entries.extend(self._retrieve_conversation(conversation_budget))

        # Long-term: relevant user knowledge
        entries.extend(self._retrieve_knowledge(query, knowledge_budget))

        # System state: relevant machine/service info
        entries.extend(self._retrieve_system_state(query, state_budget))

        return entries

    def add_conversation_turn(self, role: str, content: str) -> None:
        """Add a turn to conversation memory.

        Args:
            role: Message role (user, assistant, system).
            content: Message content.
        """
        self.short_term.add_turn(role, content)

    def learn_about_user(
        self,
        key: str,
        value: str,
        source: str = "conversation",
        tags: Optional[List[str]] = None,
    ) -> None:
        """Store user knowledge in long-term memory.

        Args:
            key: Knowledge identifier.
            value: The knowledge content.
            source: Source of this knowledge.
            tags: Optional categorization tags.
        """
        self.long_term.learn(key, value, source, tags)

    def update_machine_state(
        self,
        machine: str,
        status: str,
        host: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update system state for a machine.

        Args:
            machine: Machine identifier.
            status: New status string.
            host: Machine hostname/IP.
            metadata: Additional metadata.
        """
        self.system_state.update_state(machine, status, host, metadata)

    def save_all(self) -> None:
        """Persist all memory tiers to disk."""
        self.long_term.save()
        self.system_state.save()

    def load_all(self) -> None:
        """Load all memory tiers from disk."""
        self.long_term.load()
        self.system_state.load()

    def _retrieve_conversation(self, budget: int) -> List[MemoryEntry]:
        """Retrieve conversation context within budget.

        Args:
            budget: Token budget for conversation entries.

        Returns:
            List of MemoryEntry objects from conversation.
        """
        entries: List[MemoryEntry] = []
        tokens_used = 0

        # Include summaries if they exist
        for summary in self.short_term.summaries:
            summary_tokens = _estimate_tokens(summary)
            if tokens_used + summary_tokens > budget:
                break
            entries.append(
                MemoryEntry(
                    id=f"conv_summary_{len(entries)}",
                    content=summary,
                    category=MemoryCategory.CONVERSATION,
                    relevance_score=0.6,
                )
            )
            tokens_used += summary_tokens

        # Include recent turns
        recent = self.short_term.recent_context(budget - tokens_used)
        for i, turn in enumerate(recent):
            content = f"{turn.role}: {turn.content}"
            entry_tokens = _estimate_tokens(content)
            if tokens_used + entry_tokens > budget:
                break
            entries.append(
                MemoryEntry(
                    id=f"conv_turn_{i}",
                    content=content,
                    category=MemoryCategory.CONVERSATION,
                    relevance_score=0.8 + (i * 0.01),
                )
            )
            tokens_used += entry_tokens

        return entries

    def _retrieve_knowledge(self, query: str, budget: int) -> List[MemoryEntry]:
        """Retrieve relevant user knowledge within budget.

        Args:
            query: Search query.
            budget: Token budget for knowledge entries.

        Returns:
            List of MemoryEntry objects from long-term memory.
        """
        entries: List[MemoryEntry] = []
        tokens_used = 0

        results = self.long_term.recall(query, limit=10)
        for knowledge in results:
            content = f"{knowledge.key}: {knowledge.value}"
            entry_tokens = _estimate_tokens(content)
            if tokens_used + entry_tokens > budget:
                break
            entries.append(
                MemoryEntry(
                    id=f"knowledge_{knowledge.key}",
                    content=content,
                    category=MemoryCategory.USER_KNOWLEDGE,
                    relevance_score=knowledge.confidence,
                    metadata={"source": knowledge.source, "tags": knowledge.tags},
                )
            )
            tokens_used += entry_tokens

        return entries

    def _retrieve_system_state(self, query: str, budget: int) -> List[MemoryEntry]:
        """Retrieve relevant system state within budget.

        Args:
            query: Search query for filtering relevant states.
            budget: Token budget for state entries.

        Returns:
            List of MemoryEntry objects from system state.
        """
        entries: List[MemoryEntry] = []
        tokens_used = 0
        query_lower = query.lower()

        all_states = self.system_state.get_all_states()

        for state in all_states:
            # Score relevance to the query
            relevance = 0.5
            if state.machine_name.lower() in query_lower:
                relevance = 1.0
            elif any(s.name.lower() in query_lower for s in state.services):
                relevance = 0.9

            # Build state description
            services_str = ", ".join(f"{s.name}={s.status.value}" for s in state.services)
            content = f"Machine '{state.machine_name}' ({state.host}): status={state.status}"
            if services_str:
                content += f", services=[{services_str}]"

            entry_tokens = _estimate_tokens(content)
            if tokens_used + entry_tokens > budget:
                break

            entries.append(
                MemoryEntry(
                    id=f"state_{state.machine_name}",
                    content=content,
                    category=MemoryCategory.SYSTEM_STATE,
                    relevance_score=relevance,
                    metadata={"machine": state.machine_name, "status": state.status},
                )
            )
            tokens_used += entry_tokens

        # Sort by relevance
        entries.sort(key=lambda e: e.relevance_score, reverse=True)
        return entries
