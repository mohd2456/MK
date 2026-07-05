"""Memory system for MK.

Provides three tiers of memory:
- Short-term: current conversation with sliding window and summarization
- Long-term: user preferences, knowledge, and learned patterns (persisted to JSON)
- System state: homelab machine states and service statuses
"""

from mk.memory.manager import MemoryManager
from mk.memory.models import (
    ConversationTurn,
    MemoryEntry,
    SystemState,
    UserKnowledge,
)

__all__ = [
    "MemoryManager",
    "MemoryEntry",
    "ConversationTurn",
    "UserKnowledge",
    "SystemState",
]
