"""Vector memory subsystem — semantic recall via embeddings.

Adds semantic search to MK's memory so it can answer questions
like "what did we decide about the Plex server last month" by
finding memories with similar *meaning*, not just matching keywords.

Components:
    - VectorStore: Numpy-based embedding storage with cosine similarity
    - EmbeddingProvider: Generates embeddings (API or local TF-IDF)
    - SemanticMemory: High-level interface for store/recall by meaning
    - DecisionLog: Tracks decisions, outcomes, and learnings over time
"""

from mk.memory.vector.store import VectorStore, VectorEntry
from mk.memory.vector.embeddings import EmbeddingProvider, LocalEmbedder
from mk.memory.vector.semantic import SemanticMemory, MemoryRecord
from mk.memory.vector.decisions import DecisionLog, Decision, DecisionOutcome

__all__ = [
    "VectorStore",
    "VectorEntry",
    "EmbeddingProvider",
    "LocalEmbedder",
    "SemanticMemory",
    "MemoryRecord",
    "DecisionLog",
    "Decision",
    "DecisionOutcome",
]
