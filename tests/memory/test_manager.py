"""Tests for the unified memory manager."""

from __future__ import annotations

import tempfile

import pytest

from mk.memory.long_term import LongTermMemory
from mk.memory.manager import MemoryManager
from mk.memory.models import MemoryCategory, ServiceStatus
from mk.memory.short_term import ShortTermMemory
from mk.memory.system_state import SystemStateMemory


class TestMemoryManager:
    """Tests for the MemoryManager class."""

    def _make_manager(self) -> MemoryManager:
        """Create a MemoryManager with test configuration."""
        return MemoryManager(
            short_term=ShortTermMemory(max_messages=50, summary_threshold=20),
            long_term=LongTermMemory(storage_path="/tmp/mk_test_manager_lt"),
            system_state=SystemStateMemory(storage_path="/tmp/mk_test_manager_state"),
            context_budget=4000,
        )

    def test_init_defaults(self) -> None:
        """Default initialization creates all tiers."""
        manager = MemoryManager()
        assert manager.short_term is not None
        assert manager.long_term is not None
        assert manager.system_state is not None
        assert manager.context_budget == 8000

    def test_add_conversation_turn(self) -> None:
        """Adding a conversation turn goes to short-term memory."""
        manager = self._make_manager()
        manager.add_conversation_turn("user", "Hello MK")
        assert manager.short_term.turn_count == 1

    def test_learn_about_user(self) -> None:
        """Learning about user stores in long-term memory."""
        manager = self._make_manager()
        manager.learn_about_user("name", "Mohammed", source="introduction")
        assert manager.long_term.knowledge_count == 1
        knowledge = manager.long_term.get("name")
        assert knowledge is not None
        assert knowledge.value == "Mohammed"

    def test_update_machine_state(self) -> None:
        """Updating machine state stores in system state tier."""
        manager = self._make_manager()
        manager.update_machine_state("media-server", "online", host="192.168.1.50")
        state = manager.system_state.get_state("media-server")
        assert state is not None
        assert state.status == "online"
        assert state.host == "192.168.1.50"

    def test_retrieve_context_empty(self) -> None:
        """Retrieving context from empty memory returns empty list."""
        manager = self._make_manager()
        entries = manager.retrieve_context("tell me something")
        assert entries == []

    def test_retrieve_context_conversation(self) -> None:
        """Context retrieval includes conversation history."""
        manager = self._make_manager()
        manager.add_conversation_turn("user", "How is the media server?")
        manager.add_conversation_turn("assistant", "It is running fine.")

        entries = manager.retrieve_context("media server status")
        # Should include conversation entries
        conv_entries = [e for e in entries if e.category == MemoryCategory.CONVERSATION]
        assert len(conv_entries) > 0

    def test_retrieve_context_knowledge(self) -> None:
        """Context retrieval includes relevant user knowledge."""
        manager = self._make_manager()
        manager.learn_about_user("media_preference", "prefers 4K content")
        manager.learn_about_user("server_name", "media-box")

        entries = manager.retrieve_context("media")
        knowledge_entries = [e for e in entries if e.category == MemoryCategory.USER_KNOWLEDGE]
        assert len(knowledge_entries) > 0

    def test_retrieve_context_system_state(self) -> None:
        """Context retrieval includes system state information."""
        manager = self._make_manager()
        manager.update_machine_state("plex-server", "online", host="192.168.1.50")
        manager.system_state.update_service(
            "plex-server", "plex", ServiceStatus.RUNNING
        )

        entries = manager.retrieve_context("plex-server")
        state_entries = [e for e in entries if e.category == MemoryCategory.SYSTEM_STATE]
        assert len(state_entries) > 0

    def test_retrieve_context_all_tiers(self) -> None:
        """Context retrieval combines entries from all tiers."""
        manager = self._make_manager()

        # Populate all tiers
        manager.add_conversation_turn("user", "Check my media server")
        manager.learn_about_user("media_server_ip", "192.168.1.50")
        manager.update_machine_state("media-server", "online", host="192.168.1.50")

        entries = manager.retrieve_context("media server")

        # Should have entries from multiple categories
        categories = {e.category for e in entries}
        assert len(categories) >= 2  # At least conversation + one other

    def test_retrieve_context_respects_budget(self) -> None:
        """Context retrieval respects token budget."""
        manager = self._make_manager()

        # Add lots of content
        for i in range(30):
            manager.add_conversation_turn("user", f"Message {i} with long content here")
            manager.learn_about_user(f"fact_{i}", f"Value {i} is important")

        # Small budget should limit results
        entries = manager.retrieve_context("anything", token_budget=100)
        # We should get some entries but not all
        assert len(entries) < 60

    def test_save_and_load_all(self) -> None:
        """save_all and load_all persist both long-term and system state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lt_path = f"{tmpdir}/lt"
            state_path = f"{tmpdir}/state"

            # Save
            manager = MemoryManager(
                long_term=LongTermMemory(storage_path=lt_path),
                system_state=SystemStateMemory(storage_path=state_path),
            )
            manager.learn_about_user("key1", "value1")
            manager.update_machine_state("server1", "online")
            manager.save_all()

            # Load into new instance
            manager2 = MemoryManager(
                long_term=LongTermMemory(storage_path=lt_path),
                system_state=SystemStateMemory(storage_path=state_path),
            )
            manager2.load_all()

            assert manager2.long_term.knowledge_count == 1
            assert manager2.system_state.get_state("server1") is not None

    def test_retrieve_context_custom_budget(self) -> None:
        """Custom token budget is respected."""
        manager = self._make_manager()
        manager.add_conversation_turn("user", "Hello")

        entries_small = manager.retrieve_context("hello", token_budget=10)
        entries_large = manager.retrieve_context("hello", token_budget=10000)

        # Larger budget should potentially include more
        assert len(entries_small) <= len(entries_large)
