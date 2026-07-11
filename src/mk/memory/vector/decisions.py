"""Decision log — tracks decisions, outcomes, and learnings.

Over time, MK makes many decisions: which model to use, whether to
restart a service, how to organize files. The DecisionLog tracks:
- What was decided
- What alternatives were considered
- What the outcome was
- What was learned from the outcome

This enables MK to improve over time:
- "Last time we restarted Plex at peak hours, users complained"
- "Switching to H.265 saved 60% disk space with no quality complaints"
- "Using rsync over the private network was 3x faster than scp"
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DecisionOutcome(str, Enum):
    """Outcome of a decision after it was executed."""

    PENDING = "pending"  # Not yet evaluated
    SUCCESS = "success"  # Worked as intended
    PARTIAL = "partial"  # Partially worked
    FAILURE = "failure"  # Did not work
    UNKNOWN = "unknown"  # Can't determine


@dataclass
class Decision:
    """A recorded decision.

    Captures the full context: what was decided, why, what
    alternatives existed, and how it turned out.
    """

    id: str
    description: str  # What was decided
    reasoning: str = ""  # Why this was chosen
    alternatives: List[str] = field(default_factory=list)
    context: str = ""  # What triggered the decision
    category: str = "general"  # Domain (infra, media, security, etc.)

    # Outcome tracking
    outcome: DecisionOutcome = DecisionOutcome.PENDING
    outcome_notes: str = ""
    learning: str = ""  # What we learned from the outcome

    # Timestamps
    decided_at: float = field(default_factory=time.time)
    evaluated_at: Optional[float] = None

    # Metadata
    tags: List[str] = field(default_factory=list)
    related_decisions: List[str] = field(default_factory=list)
    confidence: float = 0.8  # How confident we were (0.0 to 1.0)

    @property
    def age_hours(self) -> float:
        """Hours since the decision was made."""
        return (time.time() - self.decided_at) / 3600

    @property
    def was_successful(self) -> bool:
        """Whether the decision outcome was positive."""
        return self.outcome in (DecisionOutcome.SUCCESS, DecisionOutcome.PARTIAL)

    def record_outcome(
        self,
        outcome: DecisionOutcome,
        notes: str = "",
        learning: str = "",
    ) -> None:
        """Record the outcome of this decision.

        Args:
            outcome: What happened.
            notes: Additional context about the outcome.
            learning: What we learned for next time.
        """
        self.outcome = outcome
        self.outcome_notes = notes
        self.learning = learning
        self.evaluated_at = time.time()

    def summary(self) -> str:
        """Human-readable decision summary."""
        icon = {
            DecisionOutcome.PENDING: "⏳",
            DecisionOutcome.SUCCESS: "✓",
            DecisionOutcome.PARTIAL: "◐",
            DecisionOutcome.FAILURE: "✗",
            DecisionOutcome.UNKNOWN: "?",
        }[self.outcome]

        lines = [f"{icon} [{self.category}] {self.description}"]
        if self.reasoning:
            lines.append(f"  Why: {self.reasoning}")
        if self.alternatives:
            lines.append(f"  Alternatives: {', '.join(self.alternatives)}")
        if self.learning:
            lines.append(f"  Learning: {self.learning}")
        return "\n".join(lines)


class DecisionLog:
    """Persistent log of all decisions MK has made.

    Enables MK to:
    - Learn from past outcomes
    - Avoid repeating mistakes
    - Reference prior decisions when making new ones
    - Explain its reasoning when asked
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        """Initialize the decision log.

        Args:
            storage_path: Directory for persistence.
        """
        self._storage_path = Path(storage_path or Path.home() / ".mk" / "memory" / "decisions")
        self._decisions: Dict[str, Decision] = {}
        self._counter: int = 0

    @property
    def count(self) -> int:
        """Number of recorded decisions."""
        return len(self._decisions)

    def record(
        self,
        description: str,
        reasoning: str = "",
        alternatives: Optional[List[str]] = None,
        context: str = "",
        category: str = "general",
        tags: Optional[List[str]] = None,
        confidence: float = 0.8,
    ) -> Decision:
        """Record a new decision.

        Args:
            description: What was decided.
            reasoning: Why this option was chosen.
            alternatives: What other options were considered.
            context: What triggered the decision.
            category: Domain category.
            tags: Tags for search/filtering.
            confidence: How confident we are (0.0 to 1.0).

        Returns:
            The recorded Decision.
        """
        self._counter += 1
        decision_id = f"dec-{self._counter:04d}"

        decision = Decision(
            id=decision_id,
            description=description,
            reasoning=reasoning,
            alternatives=alternatives or [],
            context=context,
            category=category,
            tags=tags or [],
            confidence=confidence,
        )

        self._decisions[decision_id] = decision
        return decision

    def update_outcome(
        self,
        decision_id: str,
        outcome: DecisionOutcome,
        notes: str = "",
        learning: str = "",
    ) -> Optional[Decision]:
        """Update the outcome of a decision.

        Args:
            decision_id: ID of the decision to update.
            outcome: What happened.
            notes: Outcome details.
            learning: What we learned.

        Returns:
            The updated Decision, or None if not found.
        """
        decision = self._decisions.get(decision_id)
        if decision:
            decision.record_outcome(outcome, notes, learning)
            return decision
        return None

    def find_related(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[Decision]:
        """Find decisions related to a query.

        Uses keyword matching against decision descriptions,
        reasoning, and tags.

        Args:
            query: Search query.
            category: Optional category filter.
            limit: Maximum results.

        Returns:
            Related decisions, most relevant first.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored: List[tuple] = []
        for decision in self._decisions.values():
            if category and decision.category != category:
                continue

            score = self._score_relevance(decision, query_lower, query_words)
            if score > 0:
                scored.append((score, decision))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:limit]]

    def get_learnings(
        self,
        category: Optional[str] = None,
        only_evaluated: bool = True,
    ) -> List[str]:
        """Get all learnings from past decisions.

        Useful for enriching LLM context with "things MK has learned."

        Args:
            category: Optional category filter.
            only_evaluated: Only include decisions with outcomes.

        Returns:
            List of learning strings.
        """
        learnings: List[str] = []
        for decision in self._decisions.values():
            if category and decision.category != category:
                continue
            if only_evaluated and decision.outcome == DecisionOutcome.PENDING:
                continue
            if decision.learning:
                learnings.append(decision.learning)
        return learnings

    def get_failures(self, category: Optional[str] = None) -> List[Decision]:
        """Get all failed decisions (for learning from mistakes).

        Args:
            category: Optional category filter.

        Returns:
            Failed decisions.
        """
        return [
            d
            for d in self._decisions.values()
            if d.outcome == DecisionOutcome.FAILURE and (category is None or d.category == category)
        ]

    def recent(self, limit: int = 10) -> List[Decision]:
        """Get the most recent decisions.

        Args:
            limit: Maximum to return.

        Returns:
            Recent decisions, newest first.
        """
        sorted_decisions = sorted(
            self._decisions.values(),
            key=lambda d: d.decided_at,
            reverse=True,
        )
        return sorted_decisions[:limit]

    def _score_relevance(self, decision: Decision, query_lower: str, query_words: set) -> float:
        """Score a decision's relevance to a query."""
        score = 0.0

        desc_lower = decision.description.lower()
        reasoning_lower = decision.reasoning.lower()

        # Description match
        if query_lower in desc_lower:
            score += 3.0
        desc_words = set(desc_lower.split())
        score += len(query_words & desc_words) * 0.5

        # Reasoning match
        if query_lower in reasoning_lower:
            score += 2.0
        reasoning_words = set(reasoning_lower.split())
        score += len(query_words & reasoning_words) * 0.3

        # Tag match
        for tag in decision.tags:
            if tag.lower() in query_lower:
                score += 1.5

        # Category match (if query mentions it)
        if decision.category in query_lower:
            score += 1.0

        # Boost successful decisions
        if decision.was_successful:
            score *= 1.2

        return score

    def save(self) -> None:
        """Persist decisions to disk."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        data_file = self._storage_path / "decisions.json"

        data = []
        for decision in self._decisions.values():
            data.append(
                {
                    "id": decision.id,
                    "description": decision.description,
                    "reasoning": decision.reasoning,
                    "alternatives": decision.alternatives,
                    "context": decision.context,
                    "category": decision.category,
                    "outcome": decision.outcome.value,
                    "outcome_notes": decision.outcome_notes,
                    "learning": decision.learning,
                    "decided_at": decision.decided_at,
                    "evaluated_at": decision.evaluated_at,
                    "tags": decision.tags,
                    "confidence": decision.confidence,
                }
            )

        with open(data_file, "w") as f:
            json.dump({"counter": self._counter, "decisions": data}, f, indent=2)

    def load(self) -> bool:
        """Load decisions from disk.

        Returns:
            True if loaded successfully.
        """
        data_file = self._storage_path / "decisions.json"
        if not data_file.exists():
            return False

        try:
            with open(data_file, "r") as f:
                data = json.load(f)

            self._counter = data.get("counter", 0)
            self._decisions.clear()

            for entry in data.get("decisions", []):
                decision = Decision(
                    id=entry["id"],
                    description=entry["description"],
                    reasoning=entry.get("reasoning", ""),
                    alternatives=entry.get("alternatives", []),
                    context=entry.get("context", ""),
                    category=entry.get("category", "general"),
                    outcome=DecisionOutcome(entry.get("outcome", "pending")),
                    outcome_notes=entry.get("outcome_notes", ""),
                    learning=entry.get("learning", ""),
                    decided_at=entry.get("decided_at", time.time()),
                    evaluated_at=entry.get("evaluated_at"),
                    tags=entry.get("tags", []),
                    confidence=entry.get("confidence", 0.8),
                )
                self._decisions[decision.id] = decision

            return True
        except Exception as e:
            logger.error(f"Failed to load decisions: {e}")
            return False

    def summary(self) -> str:
        """Get a formatted summary of the decision log."""
        lines = [f"Decision Log ({self.count} decisions):"]

        # Stats
        outcomes = {}
        for d in self._decisions.values():
            o = d.outcome.value
            outcomes[o] = outcomes.get(o, 0) + 1
        lines.append(f"  Outcomes: {outcomes}")

        # Recent
        recent = self.recent(5)
        if recent:
            lines.append("\n  Recent:")
            for d in recent:
                lines.append(f"    {d.summary()}")

        return "\n".join(lines)
