"""Semantic memory — recall by meaning, not keywords.

The SemanticMemory is the high-level interface that MK uses for
"intelligent recall." Instead of grep-style keyword matching,
it finds memories with similar *meaning* to the query.

Examples:
- "what did we decide about Plex?" → finds the decision about
  migrating from Plex to Jellyfin, even though "decide" isn't
  in the stored text
- "storage problems" → finds memories about disk full warnings,
  ZFS scrub errors, and pool expansion discussions

Memory types:
- Conversations: Summaries of past conversations
- Decisions: Choices made and their reasoning
- Facts: Learned information about the user/system
- Events: Things that happened (incidents, changes)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


from mk.memory.vector.embeddings import EmbeddingProvider, LocalEmbedder
from mk.memory.vector.store import VectorStore

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """Types of semantic memories."""

    CONVERSATION = "conversation"  # Past conversation summaries
    DECISION = "decision"  # Decisions made and reasoning
    FACT = "fact"  # Learned facts about user/system
    EVENT = "event"  # Things that happened
    PREFERENCE = "preference"  # User preferences
    PROCEDURE = "procedure"  # How to do things


@dataclass
class MemoryRecord:
    """A single semantic memory record.

    Contains the original content, its type, and metadata.
    The embedding is stored separately in the VectorStore.
    """

    id: str
    content: str
    memory_type: MemoryType
    created_at: float = field(default_factory=time.time)
    source: str = "conversation"  # Where this memory came from
    tags: List[str] = field(default_factory=list)
    importance: float = 1.0  # 0.0 to 1.0 (higher = more important)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Retrieval stats
    access_count: int = 0
    last_accessed: Optional[float] = None


class SemanticMemory:
    """MK's semantic memory — recall by meaning.

    Stores memories with their vector embeddings and retrieves
    them based on semantic similarity to a query. Integrates
    with the existing memory system as an upgrade layer.

    Usage:
        memory = SemanticMemory()
        memory.store("User prefers dark theme for Grafana", MemoryType.PREFERENCE)
        memory.store("Decided to use ZFS mirror for backups", MemoryType.DECISION)

        results = memory.recall("what storage setup do we use?")
        # Returns the ZFS decision with high confidence
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        embedder: Optional[EmbeddingProvider] = None,
        dimension: int = 384,
    ) -> None:
        """Initialize semantic memory.

        Args:
            storage_path: Directory for persistence.
            embedder: Embedding provider. Uses LocalEmbedder if None.
            dimension: Embedding dimension (must match embedder).
        """
        self._embedder = embedder or LocalEmbedder(dimension=dimension)
        self._dimension = dimension

        store_path = str(Path(storage_path or "~/.mk/memory/vectors").expanduser())
        self._store = VectorStore(dimension=dimension, storage_path=store_path)
        self._records: Dict[str, MemoryRecord] = {}

    @property
    def count(self) -> int:
        """Number of stored memories."""
        return self._store.count

    def store(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.FACT,
        source: str = "conversation",
        tags: Optional[List[str]] = None,
        importance: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        record_id: Optional[str] = None,
    ) -> str:
        """Store a new memory.

        Embeds the content and adds it to the vector store.

        Args:
            content: The memory content (natural language).
            memory_type: Type of memory.
            source: Where this memory came from.
            tags: Optional tags for filtering.
            importance: Importance score (0.0 to 1.0).
            metadata: Additional metadata.
            record_id: Optional custom ID.

        Returns:
            The memory record ID.
        """
        record_id = record_id or str(uuid.uuid4())[:12]

        # Create the record
        record = MemoryRecord(
            id=record_id,
            content=content,
            memory_type=memory_type,
            source=source,
            tags=tags or [],
            importance=importance,
            metadata=metadata or {},
        )
        self._records[record_id] = record

        # Generate embedding
        embedding = self._embedder.embed(content)

        # Store in vector store with metadata for filtering
        store_metadata = {
            "category": memory_type.value,
            "source": source,
            "importance": importance,
            "tags": tags or [],
        }
        if metadata:
            store_metadata.update(metadata)

        self._store.add(
            content=content,
            embedding=embedding,
            metadata=store_metadata,
            entry_id=record_id,
        )

        return record_id

    def recall(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.2,
        memory_type: Optional[MemoryType] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Recall memories semantically similar to the query.

        Args:
            query: Natural language query.
            top_k: Maximum results.
            min_score: Minimum similarity threshold.
            memory_type: Filter by memory type.
            tags: Filter by tags (any match).

        Returns:
            List of dicts with content, score, type, and metadata.
        """
        # Generate query embedding
        query_embedding = self._embedder.embed(query)

        # Search with optional category filter
        category_filter = memory_type.value if memory_type else None
        results = self._store.search(
            query_embedding,
            top_k=top_k * 2,  # Over-fetch for post-filtering
            min_score=min_score,
            category_filter=category_filter,
        )

        # Post-filter by tags if specified
        if tags:
            tag_set = set(tags)
            results = [r for r in results if tag_set & set(r.entry.metadata.get("tags", []))]

        # Build response with record data
        output: List[Dict[str, Any]] = []
        for result in results[:top_k]:
            record = self._records.get(result.entry.id)
            if record:
                record.access_count += 1
                record.last_accessed = time.time()

            output.append(
                {
                    "id": result.entry.id,
                    "content": result.entry.content,
                    "score": round(result.score, 4),
                    "type": result.entry.metadata.get("category", "unknown"),
                    "source": result.entry.metadata.get("source", "unknown"),
                    "importance": result.entry.metadata.get("importance", 1.0),
                    "tags": result.entry.metadata.get("tags", []),
                    "created_at": result.entry.created_at,
                }
            )

        return output

    def recall_formatted(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.25,
    ) -> str:
        """Recall memories and format them for LLM context.

        Returns a string ready to be injected into the system prompt
        as "What you remember about this topic."

        Args:
            query: Natural language query.
            top_k: Maximum memories to include.
            min_score: Minimum similarity.

        Returns:
            Formatted string of relevant memories.
        """
        results = self.recall(query, top_k=top_k, min_score=min_score)

        if not results:
            return ""

        lines = []
        for r in results:
            type_label = r["type"]
            score_pct = int(r["score"] * 100)
            lines.append(f"- [{type_label}] {r['content']} (relevance: {score_pct}%)")

        return "\n".join(lines)

    def forget(self, record_id: str) -> bool:
        """Remove a memory.

        Args:
            record_id: The memory to remove.

        Returns:
            True if found and removed.
        """
        self._records.pop(record_id, None)
        return self._store.remove(record_id)

    def store_conversation_summary(
        self,
        summary: str,
        topic: str = "",
        participants: Optional[List[str]] = None,
    ) -> str:
        """Store a conversation summary as a memory.

        Convenience method for the memory manager to store
        compressed conversation history.

        Args:
            summary: The conversation summary text.
            topic: Main topic of the conversation.
            participants: Who was involved.

        Returns:
            Memory record ID.
        """
        metadata = {}
        if topic:
            metadata["topic"] = topic
        if participants:
            metadata["participants"] = participants

        return self.store(
            content=summary,
            memory_type=MemoryType.CONVERSATION,
            source="conversation_summary",
            tags=[topic] if topic else [],
            metadata=metadata,
        )

    def store_decision(
        self,
        decision: str,
        reasoning: str = "",
        alternatives: Optional[List[str]] = None,
    ) -> str:
        """Store a decision with its reasoning.

        Args:
            decision: What was decided.
            reasoning: Why it was decided.
            alternatives: What other options were considered.

        Returns:
            Memory record ID.
        """
        content = decision
        if reasoning:
            content += f" (Reason: {reasoning})"

        metadata: Dict[str, Any] = {}
        if alternatives:
            metadata["alternatives"] = alternatives
        if reasoning:
            metadata["reasoning"] = reasoning

        return self.store(
            content=content,
            memory_type=MemoryType.DECISION,
            source="decision",
            importance=0.9,  # Decisions are important
            metadata=metadata,
        )

    def save(self) -> None:
        """Persist to disk."""
        self._store.save()

    def load(self) -> bool:
        """Load from disk.

        Returns:
            True if loaded successfully.
        """
        return self._store.load()

    def stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        type_counts: Dict[str, int] = {}
        for record in self._records.values():
            t = record.memory_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_memories": self.count,
            "by_type": type_counts,
            "vector_store": self._store.stats(),
        }
