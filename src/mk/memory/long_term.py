"""Long-term user knowledge store.

A key-value store for user preferences, patterns, and facts
learned over time. Backed by JSON file storage for persistence.
Includes relevance scoring for intelligent memory retrieval.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mk.memory.models import UserKnowledge


class LongTermMemory:
    """Long-term memory for user knowledge and preferences.

    Stores key-value pairs representing facts about the user,
    their preferences, learned patterns, and other persistent
    knowledge. Data is persisted to JSON files on disk.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        """Initialize long-term memory.

        Args:
            storage_path: Path to the directory for storing memory files.
                If None, uses ~/.mk/memory as default.
        """
        if storage_path:
            self._storage_path = Path(storage_path)
        else:
            self._storage_path = Path.home() / ".mk" / "memory"
        self._knowledge: Dict[str, UserKnowledge] = {}
        self._loaded = False

    @property
    def knowledge_count(self) -> int:
        """Return the number of stored knowledge entries."""
        return len(self._knowledge)

    @property
    def storage_path(self) -> Path:
        """Return the storage path."""
        return self._storage_path

    def learn(self, key: str, value: str, source: str = "conversation", tags: Optional[List[str]] = None) -> UserKnowledge:
        """Store a new piece of knowledge about the user.

        If the key already exists, updates the value and increases
        confidence (reinforcement learning).

        Args:
            key: Knowledge identifier/topic.
            value: The knowledge content.
            source: Where this knowledge came from.
            tags: Optional tags for categorization.

        Returns:
            The created or updated UserKnowledge entry.
        """
        now = datetime.utcnow()

        if key in self._knowledge:
            existing = self._knowledge[key]
            # Reinforce confidence on repeated learning
            new_confidence = min(1.0, existing.confidence + 0.1)
            self._knowledge[key] = UserKnowledge(
                key=key,
                value=value,
                confidence=new_confidence,
                learned_at=existing.learned_at,
                last_accessed=now,
                access_count=existing.access_count,
                source=source,
                tags=tags or existing.tags,
            )
        else:
            self._knowledge[key] = UserKnowledge(
                key=key,
                value=value,
                confidence=0.8,
                learned_at=now,
                last_accessed=now,
                access_count=0,
                source=source,
                tags=tags or [],
            )

        return self._knowledge[key]

    def recall(self, query: str, limit: int = 10) -> List[UserKnowledge]:
        """Retrieve relevant knowledge entries based on a query.

        Scores entries by relevance to the query using keyword
        matching and confidence weighting, returning the top results.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of relevant UserKnowledge entries, sorted by relevance.
        """
        if not self._knowledge:
            return []

        scored: List[tuple] = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for knowledge in self._knowledge.values():
            score = self._score_relevance(knowledge, query_lower, query_words)
            if score > 0:
                scored.append((score, knowledge))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Update access timestamps for returned results
        results = []
        for _, knowledge in scored[:limit]:
            knowledge.last_accessed = datetime.utcnow()
            knowledge.access_count += 1
            results.append(knowledge)

        return results

    def forget(self, key: str) -> bool:
        """Remove a piece of knowledge from memory.

        Args:
            key: The knowledge key to remove.

        Returns:
            True if the key existed and was removed, False otherwise.
        """
        if key in self._knowledge:
            del self._knowledge[key]
            return True
        return False

    def get(self, key: str) -> Optional[UserKnowledge]:
        """Get a specific knowledge entry by key.

        Args:
            key: The knowledge key to look up.

        Returns:
            The UserKnowledge entry, or None if not found.
        """
        return self._knowledge.get(key)

    def all_knowledge(self) -> List[UserKnowledge]:
        """Return all stored knowledge entries.

        Returns:
            List of all UserKnowledge entries.
        """
        return list(self._knowledge.values())

    def save(self) -> None:
        """Persist all knowledge to disk as JSON.

        Creates the storage directory if it does not exist.
        """
        self._storage_path.mkdir(parents=True, exist_ok=True)
        data_file = self._storage_path / "knowledge.json"

        data: List[Dict[str, Any]] = []
        for knowledge in self._knowledge.values():
            entry = knowledge.model_dump()
            # Convert datetime fields to ISO strings
            entry["learned_at"] = knowledge.learned_at.isoformat()
            entry["last_accessed"] = knowledge.last_accessed.isoformat()
            data.append(entry)

        with open(data_file, "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> None:
        """Load knowledge from disk.

        Reads from the JSON persistence file. If the file does not
        exist, starts with empty knowledge.
        """
        data_file = self._storage_path / "knowledge.json"
        if not data_file.exists():
            self._loaded = True
            return

        with open(data_file, "r") as f:
            data = json.load(f)

        self._knowledge.clear()
        for entry in data:
            # Convert ISO strings back to datetime
            entry["learned_at"] = datetime.fromisoformat(entry["learned_at"])
            entry["last_accessed"] = datetime.fromisoformat(entry["last_accessed"])
            knowledge = UserKnowledge(**entry)
            self._knowledge[knowledge.key] = knowledge

        self._loaded = True

    def _score_relevance(
        self,
        knowledge: UserKnowledge,
        query_lower: str,
        query_words: set,
    ) -> float:
        """Score the relevance of a knowledge entry to a query.

        Uses a combination of:
        - Exact key match (highest weight)
        - Key word overlap
        - Value content overlap
        - Tag matching
        - Confidence weighting

        Args:
            knowledge: The knowledge entry to score.
            query_lower: Lowercase query string.
            query_words: Set of query words.

        Returns:
            Relevance score (higher is more relevant).
        """
        score = 0.0
        key_lower = knowledge.key.lower()
        value_lower = knowledge.value.lower()

        # Exact key match
        if query_lower == key_lower:
            score += 5.0
        # Key contains query
        elif query_lower in key_lower:
            score += 3.0
        # Query contains key
        elif key_lower in query_lower:
            score += 2.5

        # Word overlap with key
        key_words = set(key_lower.split("_"))
        key_overlap = query_words & key_words
        score += len(key_overlap) * 1.5

        # Word overlap with value
        value_words = set(value_lower.split())
        value_overlap = query_words & value_words
        score += len(value_overlap) * 0.5

        # Tag matching
        for tag in knowledge.tags:
            if tag.lower() in query_lower:
                score += 1.0

        # Weight by confidence
        score *= knowledge.confidence

        return score
