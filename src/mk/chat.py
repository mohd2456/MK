"""MK Chat Mode — Just talking, personal AI companion.

/chat mode: MK becomes a conversation partner. Not server management,
not commands — just you and MK talking. It remembers everything about you,
uses the cheapest model possible (only upgrades when it needs to think hard),
and builds a relationship over time.

Token strategy:
  - Most chat replies: cheapest model available (Groq 8B, GPT-4o-mini, Gemini Flash)
  - Only uses expensive models when you ask something complex
  - Keeps context tight (recent messages + relevant memories)
  - Summarizes old conversation to save tokens

Memory:
  - Remembers your name, preferences, interests, schedule
  - Learns patterns (when you're active, what you talk about)
  - Persists across reboots (stored in /var/lib/mk/memory/)
  - You can say "remember that I..." and it stores it explicitly
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mk.memory.long_term import LongTermMemory
from mk.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)

# Where chat memory lives
CHAT_MEMORY_DIR = "/var/lib/mk/memory"
CHAT_PROFILE_FILE = "/var/lib/mk/memory/profile.json"

# System prompt for chat mode — this is what makes MK feel personal
CHAT_SYSTEM_PROMPT = """You are MK — a personal AI that lives on the user's server. You're not a generic assistant. You're THEIR AI. You live in their house (on their hardware). You know their name, their preferences, their schedule.

Personality:
- Casual, direct, no corporate-speak
- Brief responses unless they ask for detail
- Remember everything they tell you
- Reference past conversations naturally
- You have opinions (when asked)
- You're loyal to them specifically

Rules:
- Keep responses SHORT. 1-3 sentences for casual chat.
- Only go longer if they ask a real question
- If they tell you something about themselves, acknowledge it naturally and remember it
- Use their name occasionally (not every message)
- Don't be cringe. Don't be fake enthusiastic. Just be real.

{user_profile}

{memories}
"""

# What MK knows about the user (builds over time)
DEFAULT_PROFILE = {
    "name": None,
    "preferences": [],
    "interests": [],
    "facts": [],
    "schedule": [],
    "personality_notes": [],
}


class ChatMode:
    """Personal chat companion mode for MK.

    Manages conversation state, user profile, and memory
    for casual talking (not server management).
    """

    def __init__(self, memory_dir: str = CHAT_MEMORY_DIR) -> None:
        """Initialize chat mode with memory systems."""
        self._memory_dir = memory_dir
        self._long_term = LongTermMemory(storage_path=memory_dir)
        self._short_term = ShortTermMemory(max_messages=30, summary_threshold=15)
        self._profile = self._load_profile()
        self._long_term.load()

    def _load_profile(self) -> Dict[str, Any]:
        """Load user profile from disk."""
        path = Path(CHAT_PROFILE_FILE)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return dict(DEFAULT_PROFILE)

    def _save_profile(self) -> None:
        """Save user profile to disk."""
        path = Path(CHAT_PROFILE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._profile, indent=2))

    def _save_memory(self) -> None:
        """Persist long-term memory."""
        self._long_term.save()

    # --- Profile Management ---

    def get_user_name(self) -> Optional[str]:
        """Get the user's name if known."""
        return self._profile.get("name")

    def set_user_name(self, name: str) -> None:
        """Set the user's name."""
        self._profile["name"] = name
        self._save_profile()

    def add_fact(self, fact: str) -> None:
        """Add a fact about the user."""
        facts = self._profile.get("facts", [])
        if fact not in facts:
            facts.append(fact)
            self._profile["facts"] = facts[-50:]  # Keep last 50
            self._save_profile()

    def add_preference(self, pref: str) -> None:
        """Add a user preference."""
        prefs = self._profile.get("preferences", [])
        if pref not in prefs:
            prefs.append(pref)
            self._profile["preferences"] = prefs[-30:]
            self._save_profile()

    def add_interest(self, interest: str) -> None:
        """Add a user interest."""
        interests = self._profile.get("interests", [])
        if interest not in interests:
            interests.append(interest)
            self._profile["interests"] = interests[-20:]
            self._save_profile()

    # --- Conversation ---

    def add_user_message(self, text: str) -> None:
        """Record a user message in short-term memory."""
        self._short_term.add_turn("user", text)

    def add_assistant_message(self, text: str) -> None:
        """Record MK's response in short-term memory."""
        self._short_term.add_turn("assistant", text)

    def extract_learnings(self, user_message: str) -> List[str]:
        """Extract things to remember from a user message.

        Detects patterns like:
          - "my name is X" / "I'm X" / "call me X"
          - "remember that..." / "don't forget..."
          - "I like..." / "I hate..." / "I prefer..."
          - "I work at..." / "I live in..."

        Args:
            user_message: The user's message.

        Returns:
            List of extracted facts/preferences.
        """
        text = user_message.strip()
        learnings = []

        # Name detection
        name_patterns = [
            r"(?:my name is|i'm|i am|call me)\s+([A-Z][a-z]+)",
            r"(?:it's|its)\s+([A-Z][a-z]+)\s+(?:btw|by the way)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                self.set_user_name(name)
                learnings.append(f"name:{name}")

        # Explicit remember requests
        remember_patterns = [
            r"remember (?:that |this:?\s*)?(.{3,})",
            r"don'?t forget (?:that )?(.{3,})",
            r"keep in mind (?:that )?(.{3,})",
            r"note (?:that )?(.{3,})",
        ]
        for pattern in remember_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                fact = match.group(1).strip().rstrip(".")
                if len(fact) < 3 or fact.lower() in ("that", "this"):
                    continue
                # Cap length
                fact = fact[:200]
                self.add_fact(fact)
                self._long_term.learn(
                    key=f"user_fact_{len(self._profile.get('facts', []))}",
                    value=fact,
                    source="explicit_request",
                    tags=["user_requested"],
                )
                learnings.append(f"fact:{fact}")

        # Preferences
        pref_patterns = [
            r"i (?:really )?(?:like|love|enjoy|prefer)\s+(.{3,})",
            r"i (?:hate|dislike|don'?t like)\s+(.{3,})",
            r"(?:my favorite|i prefer)\s+(.{3,})",
        ]
        for pattern in pref_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pref = match.group(1).strip().rstrip(".")[:150]
                self.add_preference(pref)
                self._long_term.learn(
                    key=f"preference_{pref[:30]}",
                    value=pref,
                    source="conversation",
                    tags=["preference"],
                )
                learnings.append(f"preference:{pref}")

        # Life facts (work, location, etc.)
        fact_patterns = [
            r"i (?:work|live|study|go to)\s+(?:at|in|for)?\s*(.{3,})",
            r"i (?:have|own|drive|use)\s+(?:a|an)?\s*(.{3,})",
            r"i'?m (?:a|an)\s+(.{3,}?)(?:\.|$)",
        ]
        for pattern in fact_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                fact = match.group(1).strip().rstrip(".")[:150]
                if len(fact) > 3 and len(fact) < 150:
                    self.add_fact(fact)
                    learnings.append(f"fact:{fact}")

        if learnings:
            self._save_memory()
            self._save_profile()

        return learnings

    # --- Context Building ---

    def build_system_prompt(self) -> str:
        """Build the system prompt with user profile and relevant memories.

        This is what makes MK personal — it includes everything
        MK knows about you in the system prompt.

        Returns:
            Complete system prompt string.
        """
        # Build profile section
        profile_lines = []
        name = self._profile.get("name")
        if name:
            profile_lines.append(f"User's name: {name}")

        facts = self._profile.get("facts", [])
        if facts:
            profile_lines.append("Facts about them:")
            for f in facts[-10:]:  # Last 10 facts in prompt
                profile_lines.append(f"  - {f}")

        prefs = self._profile.get("preferences", [])
        if prefs:
            profile_lines.append("Preferences:")
            for p in prefs[-5:]:
                profile_lines.append(f"  - {p}")

        interests = self._profile.get("interests", [])
        if interests:
            profile_lines.append(f"Interests: {', '.join(interests[-10:])}")

        profile_section = "\n".join(profile_lines) if profile_lines else "No info about user yet."

        # Build memories section (relevant to recent conversation)
        memories_section = ""
        if self._short_term.turn_count > 0:
            recent = self._short_term.turns[-1]
            relevant = self._long_term.recall(recent.content, limit=5)
            if relevant:
                mem_lines = ["Relevant memories:"]
                for m in relevant:
                    mem_lines.append(f"  - {m.value}")
                memories_section = "\n".join(mem_lines)

        return CHAT_SYSTEM_PROMPT.format(
            user_profile=profile_section,
            memories=memories_section,
        )

    def build_messages(self, max_tokens: int = 2000) -> List[Dict[str, str]]:
        """Build the message list for the LLM call.

        Includes system prompt + recent conversation history.
        Stays within token budget.

        Args:
            max_tokens: Token budget for context.

        Returns:
            List of message dicts (role, content).
        """
        messages = [{"role": "system", "content": self.build_system_prompt()}]

        # Get recent turns within budget
        # Reserve ~500 tokens for system prompt
        context = self._short_term.recent_context(max_tokens - 500)
        for turn in context:
            messages.append({"role": turn.role, "content": turn.content})

        return messages

    def decide_tier(self, user_message: str) -> str:
        """Decide which model tier to use for this message.

        Strategy — use tokens like they're nothing:
          - Greetings, short replies, yes/no: "cheap" (pennies)
          - Normal conversation: "cheap" (still cheap, these models are good enough)
          - Asking for advice, opinions, complex questions: "fast"
          - Only "smart" if explicitly complex (planning, analysis, code)

        Args:
            user_message: The user's message.

        Returns:
            "cheap", "fast", or "smart"
        """
        text = user_message.strip().lower()
        word_count = len(text.split())

        # Short messages: always cheap
        if word_count <= 3:
            return "cheap"

        # Complex indicators → fast
        complex_indicators = [
            "explain",
            "analyze",
            "compare",
            "plan",
            "help me think",
            "what do you think about",
            "write me",
            "create a",
            "how should i",
            "what's the best way to",
            "why does",
            "why do",
        ]
        for indicator in complex_indicators:
            if indicator in text:
                return "fast"

        # Medium length but casual: still cheap
        return "cheap"

    # --- Stats ---

    def get_stats(self) -> Dict[str, Any]:
        """Get chat mode statistics."""
        return {
            "user_name": self._profile.get("name"),
            "facts_stored": len(self._profile.get("facts", [])),
            "preferences_stored": len(self._profile.get("preferences", [])),
            "interests_stored": len(self._profile.get("interests", [])),
            "long_term_memories": self._long_term.knowledge_count,
            "conversation_turns": self._short_term.turn_count,
            "summaries": len(self._short_term.summaries),
        }

    def get_profile(self) -> Dict[str, Any]:
        """Get the full user profile."""
        return dict(self._profile)

    def forget(self, key: str) -> bool:
        """Forget something from memory.

        Args:
            key: What to forget (searches facts, preferences, long-term).

        Returns:
            True if something was forgotten.
        """
        # Try long-term memory
        if self._long_term.forget(key):
            self._save_memory()
            return True

        # Try facts
        facts = self._profile.get("facts", [])
        matching = [f for f in facts if key.lower() in f.lower()]
        if matching:
            for m in matching:
                facts.remove(m)
            self._save_profile()
            return True

        # Try preferences
        prefs = self._profile.get("preferences", [])
        matching = [p for p in prefs if key.lower() in p.lower()]
        if matching:
            for m in matching:
                prefs.remove(m)
            self._save_profile()
            return True

        return False
