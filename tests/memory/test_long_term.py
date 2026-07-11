"""Tests for long-term user knowledge memory."""

from __future__ import annotations

import tempfile
from pathlib import Path


from mk.memory.long_term import LongTermMemory


class TestLongTermMemory:
    """Tests for the LongTermMemory class."""

    def test_init_empty(self) -> None:
        """New instance starts empty."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        assert mem.knowledge_count == 0

    def test_learn_new_fact(self) -> None:
        """Learning a new fact stores it with default confidence."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        result = mem.learn("favorite_color", "blue", source="conversation")
        assert result.key == "favorite_color"
        assert result.value == "blue"
        assert result.confidence == 0.8
        assert result.source == "conversation"
        assert mem.knowledge_count == 1

    def test_learn_with_tags(self) -> None:
        """Learning with tags stores them correctly."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        result = mem.learn(
            "preferred_editor", "vim", source="explicit", tags=["tools", "preference"]
        )
        assert result.tags == ["tools", "preference"]

    def test_learn_reinforcement(self) -> None:
        """Learning the same key again increases confidence."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("name", "Mohammed")
        first_confidence = mem.get("name").confidence

        mem.learn("name", "Mohammed")
        second_confidence = mem.get("name").confidence

        assert second_confidence > first_confidence

    def test_learn_confidence_cap(self) -> None:
        """Confidence never exceeds 1.0."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        # Learn the same thing many times
        for _ in range(20):
            mem.learn("certainty", "very sure")

        assert mem.get("certainty").confidence <= 1.0

    def test_recall_relevant_results(self) -> None:
        """recall returns entries relevant to the query."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("favorite_color", "blue")
        mem.learn("favorite_food", "pizza")
        mem.learn("home_ip", "192.168.1.100")

        results = mem.recall("color")
        assert len(results) > 0
        assert results[0].key == "favorite_color"

    def test_recall_empty_memory(self) -> None:
        """recall on empty memory returns empty list."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        results = mem.recall("anything")
        assert results == []

    def test_recall_updates_access_count(self) -> None:
        """Recalling knowledge updates access count."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("test_key", "test_value")

        mem.recall("test_key")
        knowledge = mem.get("test_key")
        assert knowledge.access_count == 1

    def test_recall_relevance_ranking(self) -> None:
        """More relevant results rank higher."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("media_server", "runs Plex and Sonarr")
        mem.learn("server_location", "in the closet")
        mem.learn("favorite_movie", "Inception")

        results = mem.recall("media server")
        # media_server should rank highest (exact word match in key)
        assert results[0].key == "media_server"

    def test_forget_existing(self) -> None:
        """Forgetting an existing key removes it."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("to_forget", "temporary")
        assert mem.knowledge_count == 1

        result = mem.forget("to_forget")
        assert result is True
        assert mem.knowledge_count == 0

    def test_forget_nonexistent(self) -> None:
        """Forgetting a nonexistent key returns False."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        result = mem.forget("nonexistent")
        assert result is False

    def test_get_existing(self) -> None:
        """get returns the knowledge entry for an existing key."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("key1", "value1")
        result = mem.get("key1")
        assert result is not None
        assert result.value == "value1"

    def test_get_nonexistent(self) -> None:
        """get returns None for a nonexistent key."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        result = mem.get("nonexistent")
        assert result is None

    def test_persistence_save_and_load(self) -> None:
        """Knowledge persists across save/load cycles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save
            mem = LongTermMemory(storage_path=tmpdir)
            mem.learn("persist_key", "persist_value", tags=["test"])
            mem.save()

            # Verify file exists
            data_file = Path(tmpdir) / "knowledge.json"
            assert data_file.exists()

            # Load into new instance
            mem2 = LongTermMemory(storage_path=tmpdir)
            mem2.load()
            assert mem2.knowledge_count == 1
            knowledge = mem2.get("persist_key")
            assert knowledge is not None
            assert knowledge.value == "persist_value"
            assert knowledge.tags == ["test"]

    def test_load_nonexistent_file(self) -> None:
        """Loading from nonexistent path starts empty."""
        mem = LongTermMemory(storage_path="/tmp/mk_nonexistent_path_xyz")
        mem.load()
        assert mem.knowledge_count == 0

    def test_all_knowledge(self) -> None:
        """all_knowledge returns all stored entries."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        mem.learn("key1", "value1")
        mem.learn("key2", "value2")
        mem.learn("key3", "value3")

        all_items = mem.all_knowledge()
        assert len(all_items) == 3

    def test_recall_with_limit(self) -> None:
        """recall respects the limit parameter."""
        mem = LongTermMemory(storage_path="/tmp/mk_test_memory")
        for i in range(10):
            mem.learn(f"server_{i}", f"IP is 192.168.1.{i}", tags=["server"])

        results = mem.recall("server", limit=3)
        assert len(results) <= 3
