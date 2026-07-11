"""Persistent chat history store.

A small, self-contained SQLite-backed store for conversational history, keyed
by an opaque ``session_id`` supplied by the client. It lets the web UI restore
a conversation after a reload or restart, independently of the engine's
in-memory conversation buffer.

Design notes:
    * A single :mod:`aiosqlite` connection is opened lazily and kept open for
      the store's lifetime. This makes an in-memory database (``:memory:``,
      the default) behave like a real, durable store for the process lifetime,
      which is ideal for tests and for deployments that don't want a file.
    * All writes are best-effort from the caller's perspective: the web layer
      wraps persistence in try/except so history never breaks a chat response.
    * Per-session history is bounded (``max_messages_per_session``) so memory
      and disk stay predictable.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


class ChatHistoryStore:
    """Async SQLite store for per-session chat history."""

    def __init__(self, db_path: str = ":memory:", max_messages_per_session: int = 200) -> None:
        """Initialize the store.

        Args:
            db_path: SQLite path. ``":memory:"`` (default) keeps history for the
                process lifetime; a file path makes it durable across restarts.
            max_messages_per_session: Upper bound on retained messages per
                session; older messages are pruned on write.
        """
        self._db_path = db_path
        self._max = max(1, int(max_messages_per_session))
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> aiosqlite.Connection:
        """Open the connection and create the schema on first use."""
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is not None:
                return self._conn
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(self._db_path)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ok INTEGER NOT NULL DEFAULT 1,
                    failure_type TEXT,
                    actions TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, id)"
            )
            await conn.commit()
            self._conn = conn
            return conn

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        ok: bool = True,
        failure_type: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Append a message to a session and prune to the retention bound."""
        if not session_id:
            return
        conn = await self._ensure()
        await conn.execute(
            """
            INSERT INTO chat_messages
                (session_id, role, content, ok, failure_type, actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                1 if ok else 0,
                failure_type,
                json.dumps(actions) if actions else None,
                datetime.now(UTC).isoformat(),
            ),
        )
        # Prune anything beyond the most recent ``_max`` for this session.
        await conn.execute(
            """
            DELETE FROM chat_messages
            WHERE session_id = ?
              AND id NOT IN (
                SELECT id FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
              )
            """,
            (session_id, session_id, self._max),
        )
        await conn.commit()

    async def get_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return up to ``limit`` most-recent messages, oldest-first."""
        if not session_id:
            return []
        conn = await self._ensure()
        limit = max(1, min(int(limit), self._max))
        cursor = await conn.execute(
            """
            SELECT role, content, ok, failure_type, actions, created_at
            FROM (
                SELECT * FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        messages: List[Dict[str, Any]] = []
        for role, content, ok, failure_type, actions, created_at in rows:
            parsed_actions: List[Dict[str, Any]] = []
            if actions:
                try:
                    parsed_actions = json.loads(actions)
                except (json.JSONDecodeError, ValueError):
                    parsed_actions = []
            messages.append(
                {
                    "role": role,
                    "content": content,
                    "ok": bool(ok),
                    "failure_type": failure_type,
                    "actions": parsed_actions,
                    "timestamp": created_at,
                }
            )
        return messages

    async def clear(self, session_id: str) -> None:
        """Delete all messages for a session."""
        if not session_id:
            return
        conn = await self._ensure()
        await conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        await conn.commit()

    async def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
