"""Vector store — lightweight embedding storage with similarity search.

A zero-dependency (except numpy) vector database for MK. Stores embeddings
alongside metadata and supports:
- Cosine similarity search (nearest neighbors)
- Metadata filtering
- Persistence to disk (numpy binary format)
- Incremental updates (add/remove without rebuilding)

Why not use a full vector DB?
- MK runs on a homelab — no separate service to manage
- Memory needs are modest (thousands, not millions of vectors)
- Numpy is fast enough for this scale
- Zero network overhead, zero latency

For production scaling beyond ~100K vectors, swap this for
sqlite-vss or qdrant. The interface is the same.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VectorEntry:
    """A single entry in the vector store.

    Combines the embedding vector with metadata for filtering
    and the original content for retrieval.
    """

    id: str
    content: str  # Original text that was embedded
    embedding: np.ndarray  # The vector embedding
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: Optional[float] = None

    @property
    def category(self) -> str:
        """Get the category from metadata."""
        return self.metadata.get("category", "general")


@dataclass
class SearchResult:
    """Result of a similarity search."""

    entry: VectorEntry
    score: float  # Cosine similarity (0.0 to 1.0)

    @property
    def content(self) -> str:
        return self.entry.content

    @property
    def id(self) -> str:
        return self.entry.id


class VectorStore:
    """Lightweight numpy-based vector store.

    Stores embedding vectors and performs cosine similarity search.
    Designed for homelab scale (hundreds to low thousands of entries).

    Performance characteristics:
    - Add: O(1)
    - Search: O(n) with numpy vectorization (fast for n < 100K)
    - Memory: ~1KB per entry for 384-dim embeddings
    - Disk: Binary numpy format, fast load/save
    """

    def __init__(
        self,
        dimension: int = 384,
        storage_path: Optional[str] = None,
    ) -> None:
        """Initialize the vector store.

        Args:
            dimension: Embedding dimension (must match embedder output).
            storage_path: Directory for persistence. None = in-memory only.
        """
        self._dimension = dimension
        self._storage_path = Path(storage_path) if storage_path else None
        self._entries: Dict[str, VectorEntry] = {}

        # Cached numpy matrix for fast batch search
        self._matrix: Optional[np.ndarray] = None
        self._id_index: List[str] = []  # Maps matrix row → entry ID
        self._dirty: bool = False  # Whether matrix needs rebuild

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        return self._dimension

    @property
    def count(self) -> int:
        """Number of stored entries."""
        return len(self._entries)

    def add(
        self,
        content: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
        entry_id: Optional[str] = None,
    ) -> str:
        """Add a new entry to the store.

        Args:
            content: Original text content.
            embedding: Vector embedding (must match store dimension).
            metadata: Optional metadata for filtering.
            entry_id: Optional custom ID (generated if not provided).

        Returns:
            The entry ID.

        Raises:
            ValueError: If embedding dimension doesn't match.
        """
        if embedding.shape[0] != self._dimension:
            raise ValueError(
                f"Embedding dimension mismatch: got {embedding.shape[0]}, "
                f"expected {self._dimension}"
            )

        entry_id = entry_id or str(uuid.uuid4())[:12]

        # Normalize the embedding for cosine similarity
        norm = np.linalg.norm(embedding)
        if norm > 0:
            normalized = embedding / norm
        else:
            normalized = embedding

        entry = VectorEntry(
            id=entry_id,
            content=content,
            embedding=normalized,
            metadata=metadata or {},
        )

        self._entries[entry_id] = entry
        self._dirty = True  # Matrix needs rebuild

        return entry_id

    def remove(self, entry_id: str) -> bool:
        """Remove an entry by ID.

        Args:
            entry_id: The entry to remove.

        Returns:
            True if found and removed.
        """
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._dirty = True
            return True
        return False

    def get(self, entry_id: str) -> Optional[VectorEntry]:
        """Get an entry by ID."""
        return self._entries.get(entry_id)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        min_score: float = 0.0,
        category_filter: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search for similar entries using cosine similarity.

        Args:
            query_embedding: The query vector.
            top_k: Maximum results to return.
            min_score: Minimum similarity score (0.0 to 1.0).
            category_filter: Only return entries with this category.
            metadata_filter: Only return entries matching these metadata keys.

        Returns:
            List of SearchResult sorted by score (highest first).
        """
        if not self._entries:
            return []

        # Normalize query
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_normalized = query_embedding / norm
        else:
            return []

        # Rebuild matrix if dirty
        if self._dirty or self._matrix is None:
            self._rebuild_matrix()

        # Compute all cosine similarities at once (fast with numpy)
        scores = self._matrix @ query_normalized

        # Get top-k indices
        if len(scores) <= top_k:
            top_indices = np.argsort(scores)[::-1]
        else:
            # Partial sort for efficiency
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        # Build results with filtering
        results: List[SearchResult] = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < min_score:
                break

            entry_id = self._id_index[idx]
            entry = self._entries[entry_id]

            # Apply filters
            if category_filter and entry.category != category_filter:
                continue
            if metadata_filter:
                if not all(entry.metadata.get(k) == v for k, v in metadata_filter.items()):
                    continue

            # Update access stats
            entry.access_count += 1
            entry.last_accessed = time.time()

            results.append(SearchResult(entry=entry, score=score))

            if len(results) >= top_k:
                break

        return results

    def search_by_text(
        self,
        query_text: str,
        embedder: Any,
        top_k: int = 10,
        min_score: float = 0.3,
        **filters: Any,
    ) -> List[SearchResult]:
        """Convenience: embed a text query and search.

        Args:
            query_text: Natural language query.
            embedder: Object with .embed(text) method.
            top_k: Maximum results.
            min_score: Minimum similarity.
            **filters: Passed to search() as metadata_filter.

        Returns:
            Search results.
        """
        query_embedding = embedder.embed(query_text)
        return self.search(
            query_embedding,
            top_k=top_k,
            min_score=min_score,
            metadata_filter=filters if filters else None,
        )

    def _rebuild_matrix(self) -> None:
        """Rebuild the numpy matrix from current entries."""
        if not self._entries:
            self._matrix = np.zeros((0, self._dimension))
            self._id_index = []
            self._dirty = False
            return

        self._id_index = list(self._entries.keys())
        embeddings = [self._entries[eid].embedding for eid in self._id_index]
        self._matrix = np.vstack(embeddings)
        self._dirty = False

    def save(self) -> None:
        """Persist the store to disk.

        Saves:
        - embeddings.npy: The embedding matrix
        - metadata.json: Entry metadata, content, and IDs
        """
        if not self._storage_path:
            return

        self._storage_path.mkdir(parents=True, exist_ok=True)

        # Rebuild matrix for consistent state
        if self._dirty:
            self._rebuild_matrix()

        # Save embeddings as numpy binary
        if self._matrix is not None and len(self._matrix) > 0:
            np.save(self._storage_path / "embeddings.npy", self._matrix)

        # Save metadata as JSON
        entries_data = []
        for entry_id in self._id_index:
            entry = self._entries[entry_id]
            entries_data.append(
                {
                    "id": entry.id,
                    "content": entry.content,
                    "metadata": entry.metadata,
                    "created_at": entry.created_at,
                    "access_count": entry.access_count,
                    "last_accessed": entry.last_accessed,
                }
            )

        with open(self._storage_path / "metadata.json", "w") as f:
            json.dump(
                {
                    "dimension": self._dimension,
                    "count": len(entries_data),
                    "entries": entries_data,
                },
                f,
                indent=2,
            )

        logger.debug(f"VectorStore saved: {self.count} entries to {self._storage_path}")

    def load(self) -> bool:
        """Load the store from disk.

        Returns:
            True if loaded successfully, False if no data found.
        """
        if not self._storage_path:
            return False

        embeddings_path = self._storage_path / "embeddings.npy"
        metadata_path = self._storage_path / "metadata.json"

        if not embeddings_path.exists() or not metadata_path.exists():
            return False

        try:
            # Load embeddings
            matrix = np.load(embeddings_path)

            # Validate dimension matches
            if matrix.ndim == 2 and matrix.shape[1] != self._dimension:
                logger.error(
                    f"VectorStore dimension mismatch: file has {matrix.shape[1]}, "
                    f"store expects {self._dimension}. Data not loaded."
                )
                return False

            # Load metadata
            with open(metadata_path, "r") as f:
                data = json.load(f)

            # Reconstruct entries
            self._entries.clear()
            entries_data = data.get("entries", [])

            for i, entry_data in enumerate(entries_data):
                if i >= len(matrix):
                    break

                entry = VectorEntry(
                    id=entry_data["id"],
                    content=entry_data["content"],
                    embedding=matrix[i],
                    metadata=entry_data.get("metadata", {}),
                    created_at=entry_data.get("created_at", time.time()),
                    access_count=entry_data.get("access_count", 0),
                    last_accessed=entry_data.get("last_accessed"),
                )
                self._entries[entry.id] = entry

            self._matrix = matrix
            self._id_index = [e["id"] for e in entries_data[: len(matrix)]]
            self._dirty = False

            logger.info(f"VectorStore loaded: {self.count} entries from {self._storage_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load VectorStore: {e}")
            return False

    def stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        return {
            "count": self.count,
            "dimension": self._dimension,
            "storage_path": str(self._storage_path) if self._storage_path else None,
            "memory_mb": (self._matrix.nbytes / (1024 * 1024) if self._matrix is not None else 0.0),
        }
