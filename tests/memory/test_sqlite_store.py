"""Tests for SQLiteMemoryStore.

Tests CRUD operations, search functionality, and concurrent access.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mk.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Create a temporary database path."""
    return str(tmp_path / "test_memories.db")


@pytest.fixture
async def store(tmp_db_path: str) -> SQLiteMemoryStore:
    """Create an initialized SQLiteMemoryStore."""
    s = SQLiteMemoryStore(db_path=tmp_db_path)
    await s.initialize()
    return s


class TestSQLiteMemoryStoreInit:
    """Test initialization and schema creation."""

    async def test_initialize_creates_db_file(self, tmp_db_path: str) -> None:
        """Database file is created on initialize."""
        store = SQLiteMemoryStore(db_path=tmp_db_path)
        await store.initialize()
        assert Path(tmp_db_path).exists()

    async def test_initialize_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Parent directories are created if they do not exist."""
        db_path = str(tmp_path / "nested" / "dir" / "test.db")
        store = SQLiteMemoryStore(db_path=db_path)
        await store.initialize()
        assert Path(db_path).exists()

    async def test_double_initialize_is_safe(self, tmp_db_path: str) -> None:
        """Calling initialize twice does not error."""
        store = SQLiteMemoryStore(db_path=tmp_db_path)
        await store.initialize()
        await store.initialize()
        assert Path(tmp_db_path).exists()

    async def test_default_path(self) -> None:
        """Default path is set to ~/.mk/memory/memories.db."""
        store = SQLiteMemoryStore()
        expected = Path.home() / ".mk" / "memory" / "memories.db"
        assert store.db_path == expected


class TestSQLiteMemoryStoreCRUD:
    """Test store, retrieve, delete operations."""

    async def test_store_and_retrieve(self, store: SQLiteMemoryStore) -> None:
        """Storing an entry and retrieving it returns the correct data."""
        await store.store("greeting", "Hello, world!", {"source": "test"})
        result = await store.retrieve("greeting")

        assert result is not None
        assert result["key"] == "greeting"
        assert result["value"] == "Hello, world!"
        assert result["metadata"] == {"source": "test"}

    async def test_retrieve_nonexistent_key(self, store: SQLiteMemoryStore) -> None:
        """Retrieving a key that does not exist returns None."""
        result = await store.retrieve("nonexistent")
        assert result is None

    async def test_store_updates_existing_key(self, store: SQLiteMemoryStore) -> None:
        """Storing with an existing key updates the value (upsert)."""
        await store.store("color", "blue")
        await store.store("color", "red")

        result = await store.retrieve("color")
        assert result is not None
        assert result["value"] == "red"

    async def test_store_with_metadata(self, store: SQLiteMemoryStore) -> None:
        """Metadata is correctly stored and retrieved as a dict."""
        metadata = {"confidence": 0.9, "tags": ["preference", "food"]}
        await store.store("favorite_food", "pizza", metadata)

        result = await store.retrieve("favorite_food")
        assert result is not None
        assert result["metadata"]["confidence"] == 0.9
        assert result["metadata"]["tags"] == ["preference", "food"]

    async def test_store_without_metadata(self, store: SQLiteMemoryStore) -> None:
        """Storing without metadata results in empty dict."""
        await store.store("simple_key", "simple_value")
        result = await store.retrieve("simple_key")
        assert result is not None
        assert result["metadata"] == {}

    async def test_delete_existing_key(self, store: SQLiteMemoryStore) -> None:
        """Deleting an existing key returns True and removes entry."""
        await store.store("temp", "temporary data")
        deleted = await store.delete("temp")
        assert deleted is True

        result = await store.retrieve("temp")
        assert result is None

    async def test_delete_nonexistent_key(self, store: SQLiteMemoryStore) -> None:
        """Deleting a key that does not exist returns False."""
        deleted = await store.delete("ghost_key")
        assert deleted is False

    async def test_store_returns_id(self, store: SQLiteMemoryStore) -> None:
        """Store method returns a non-empty string ID."""
        entry_id = await store.store("test_key", "test_value")
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0


class TestSQLiteMemoryStoreSearch:
    """Test search functionality."""

    async def test_search_by_key(self, store: SQLiteMemoryStore) -> None:
        """Search finds entries by key match."""
        await store.store("favorite_color", "blue")
        await store.store("favorite_food", "pizza")
        await store.store("work_schedule", "9 to 5")

        results = await store.search("favorite")
        assert len(results) == 2
        keys = [r["key"] for r in results]
        assert "favorite_color" in keys
        assert "favorite_food" in keys

    async def test_search_by_value(self, store: SQLiteMemoryStore) -> None:
        """Search finds entries by value content."""
        await store.store("language", "python is my favorite language")
        await store.store("editor", "I use vim for editing")

        results = await store.search("python")
        assert len(results) >= 1
        assert results[0]["key"] == "language"

    async def test_search_case_insensitive(self, store: SQLiteMemoryStore) -> None:
        """Search is case-insensitive."""
        await store.store("name", "John Smith")

        results = await store.search("JOHN")
        assert len(results) == 1
        assert results[0]["value"] == "John Smith"

    async def test_search_with_limit(self, store: SQLiteMemoryStore) -> None:
        """Search respects the limit parameter."""
        for i in range(10):
            await store.store(f"item_{i}", f"data item number {i}")

        results = await store.search("item", limit=3)
        assert len(results) == 3

    async def test_search_no_results(self, store: SQLiteMemoryStore) -> None:
        """Search returns empty list when nothing matches."""
        await store.store("greeting", "hello world")

        results = await store.search("zzzznotfound")
        assert results == []

    async def test_search_empty_store(self, store: SQLiteMemoryStore) -> None:
        """Search on empty store returns empty list."""
        results = await store.search("anything")
        assert results == []


class TestSQLiteMemoryStoreListAll:
    """Test list_all functionality."""

    async def test_list_all_empty(self, store: SQLiteMemoryStore) -> None:
        """list_all on empty store returns empty list."""
        results = await store.list_all()
        assert results == []

    async def test_list_all_returns_all_entries(self, store: SQLiteMemoryStore) -> None:
        """list_all returns all stored entries."""
        await store.store("key1", "value1")
        await store.store("key2", "value2")
        await store.store("key3", "value3")

        results = await store.list_all()
        assert len(results) == 3
        keys = {r["key"] for r in results}
        assert keys == {"key1", "key2", "key3"}


class TestSQLiteMemoryStoreConcurrency:
    """Test concurrent access patterns."""

    async def test_concurrent_writes(self, tmp_db_path: str) -> None:
        """Multiple concurrent writes do not corrupt the database."""
        store = SQLiteMemoryStore(db_path=tmp_db_path)
        await store.initialize()

        async def write_entry(i: int) -> None:
            await store.store(f"concurrent_{i}", f"value_{i}")

        # Run 20 concurrent writes
        tasks = [write_entry(i) for i in range(20)]
        await asyncio.gather(*tasks)

        results = await store.list_all()
        assert len(results) == 20

    async def test_concurrent_reads_and_writes(self, tmp_db_path: str) -> None:
        """Concurrent reads and writes work without errors."""
        store = SQLiteMemoryStore(db_path=tmp_db_path)
        await store.initialize()

        # Pre-populate
        for i in range(5):
            await store.store(f"pre_{i}", f"pre_value_{i}")

        async def reader(key: str) -> None:
            await store.retrieve(key)

        async def writer(i: int) -> None:
            await store.store(f"new_{i}", f"new_value_{i}")

        # Mix reads and writes
        tasks = []
        for i in range(5):
            tasks.append(reader(f"pre_{i}"))
            tasks.append(writer(i))

        await asyncio.gather(*tasks)

        results = await store.list_all()
        assert len(results) == 10  # 5 pre + 5 new

    async def test_concurrent_search(self, tmp_db_path: str) -> None:
        """Multiple concurrent searches work correctly."""
        store = SQLiteMemoryStore(db_path=tmp_db_path)
        await store.initialize()

        for i in range(10):
            await store.store(f"item_{i}", f"search target {i}")

        async def search_task(query: str) -> list:
            return await store.search(query)

        tasks = [search_task("item") for _ in range(10)]
        results = await asyncio.gather(*tasks)

        for result in results:
            assert len(result) == 10
