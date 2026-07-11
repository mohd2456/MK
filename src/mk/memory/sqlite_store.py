"""SQLite-backed memory store for long-term memory persistence.

Provides async CRUD and search operations for memory entries
using aiosqlite. Supports concurrent access and full-text search
via keyword matching on stored values and metadata.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


class SQLiteMemoryStore:
    """Async SQLite store for long-term memory entries.

    Schema:
        memories (
            id TEXT PRIMARY KEY,
            key TEXT,
            value TEXT,
            metadata JSON,
            embedding BLOB,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )

    Provides store, retrieve, search, delete, and list_all operations.
    All methods are async for non-blocking I/O.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the SQLite memory store.

        Args:
            db_path: Path to the SQLite database file.
                If None, uses ~/.mk/memory/memories.db
        """
        if db_path:
            self._db_path = Path(db_path)
        else:
            self._db_path = Path.home() / ".mk" / "memory" / "memories.db"
        self._initialized = False

    @property
    def db_path(self) -> Path:
        """Return the database file path."""
        return self._db_path

    async def initialize(self) -> None:
        """Create the database schema if it does not exist.

        Creates the memories table and indexes. Safe to call multiple times.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    metadata JSON,
                    embedding BLOB,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_key ON memories (key)
            """)
            await db.commit()
        self._initialized = True

    async def _ensure_initialized(self) -> None:
        """Ensure the database is initialized before operations."""
        if not self._initialized:
            await self.initialize()

    async def store(
        self,
        key: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a memory entry.

        If a key already exists, it will be updated (upsert behavior).

        Args:
            key: The memory key identifier.
            value: The memory content.
            metadata: Optional metadata dictionary.

        Returns:
            The ID of the stored entry.
        """
        await self._ensure_initialized()

        now = datetime.utcnow().isoformat()
        entry_id = f"mem_{key}_{int(time.time() * 1000)}"
        metadata_json = json.dumps(metadata or {})

        async with aiosqlite.connect(str(self._db_path)) as db:
            # Check if key exists - update if so
            cursor = await db.execute("SELECT id, created_at FROM memories WHERE key = ?", (key,))
            existing = await cursor.fetchone()

            if existing:
                entry_id = existing[0]
                await db.execute(
                    """
                    UPDATE memories
                    SET value = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (value, metadata_json, now, entry_id),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO memories (id, key, value, metadata, embedding, created_at, updated_at)
                    VALUES (?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (entry_id, key, value, metadata_json, now, now),
                )
            await db.commit()

        return entry_id

    async def retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a memory entry by key.

        Args:
            key: The memory key to look up.

        Returns:
            Dictionary with entry data, or None if not found.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM memories WHERE key = ?", (key,))
            row = await cursor.fetchone()

            if row is None:
                return None

            return {
                "id": row["id"],
                "key": row["key"],
                "value": row["value"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search memory entries by keyword matching.

        Searches both keys and values for the query string.
        Results are ordered by relevance (key matches first, then value matches).

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching entries.
        """
        await self._ensure_initialized()

        results: List[Dict[str, Any]] = []
        query_lower = query.lower()

        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            # Search key and value using LIKE
            cursor = await db.execute(
                """
                SELECT *,
                    CASE
                        WHEN LOWER(key) = ? THEN 3
                        WHEN LOWER(key) LIKE ? THEN 2
                        WHEN LOWER(value) LIKE ? THEN 1
                        ELSE 0
                    END as relevance
                FROM memories
                WHERE LOWER(key) LIKE ? OR LOWER(value) LIKE ?
                ORDER BY relevance DESC, updated_at DESC
                LIMIT ?
                """,
                (
                    query_lower,
                    f"%{query_lower}%",
                    f"%{query_lower}%",
                    f"%{query_lower}%",
                    f"%{query_lower}%",
                    limit,
                ),
            )
            rows = await cursor.fetchall()

            for row in rows:
                results.append(
                    {
                        "id": row["id"],
                        "key": row["key"],
                        "value": row["value"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )

        return results

    async def delete(self, key: str) -> bool:
        """Delete a memory entry by key.

        Args:
            key: The memory key to delete.

        Returns:
            True if an entry was deleted, False if not found.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(str(self._db_path)) as db:
            cursor = await db.execute("DELETE FROM memories WHERE key = ?", (key,))
            await db.commit()
            return cursor.rowcount > 0

    async def list_all(self) -> List[Dict[str, Any]]:
        """List all memory entries.

        Returns:
            List of all stored entries, ordered by updated_at descending.
        """
        await self._ensure_initialized()

        results: List[Dict[str, Any]] = []

        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM memories ORDER BY updated_at DESC")
            rows = await cursor.fetchall()

            for row in rows:
                results.append(
                    {
                        "id": row["id"],
                        "key": row["key"],
                        "value": row["value"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )

        return results

    async def close(self) -> None:
        """Close the store (no-op since we use context managers per operation)."""
        pass
