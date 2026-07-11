"""Embedding providers — generate vector representations of text.

Supports multiple embedding strategies:
1. LocalEmbedder: TF-IDF based (zero API cost, zero latency, decent quality)
2. API-based: OpenAI, Cohere, etc. (higher quality, costs tokens)

The LocalEmbedder uses a TF-IDF approach with hashing to create
fixed-dimension vectors from text. It's not as good as transformer
embeddings, but it's:
- Free (no API calls)
- Fast (pure numpy, no model loading)
- Good enough for homelab-scale memory (hundreds of entries)
- Deterministic (same text = same embedding)

For better quality, configure an API embedder. The SemanticMemory
class handles the abstraction — swap providers without changing code.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Dict, List, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers.

    Any class with an embed() method that returns a numpy array
    can be used as an embedding provider.
    """

    def embed(self, text: str) -> np.ndarray:
        """Generate an embedding vector for text.

        Args:
            text: Input text to embed.

        Returns:
            Numpy array of shape (dimension,).
        """
        ...

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            Numpy array of shape (len(texts), dimension).
        """
        ...

    @property
    def dimension(self) -> int:
        """Output embedding dimension."""
        ...


class LocalEmbedder:
    """Local TF-IDF based embedder — no API calls needed.

    Creates embeddings using:
    1. Text preprocessing (lowercase, tokenize, remove stopwords)
    2. Hashed n-gram features (unigrams + bigrams)
    3. TF-IDF-like weighting with sublinear TF
    4. L2 normalization

    The hashing trick gives us fixed-dimension vectors without
    needing to maintain a vocabulary. Quality is surprisingly good
    for semantic similarity when texts share domain vocabulary
    (which homelab conversations do).

    Dimension: 384 (matches common sentence-transformer output size
    for easy swapping later).
    """

    def __init__(self, dimension: int = 384) -> None:
        """Initialize the local embedder.

        Args:
            dimension: Output embedding dimension.
        """
        self._dimension = dimension
        self._stopwords = self._build_stopwords()

    @property
    def dimension(self) -> int:
        """Output embedding dimension."""
        return self._dimension

    def embed(self, text: str) -> np.ndarray:
        """Generate an embedding for a single text.

        Args:
            text: Input text.

        Returns:
            Normalized embedding vector of shape (dimension,).
        """
        if not text or not text.strip():
            return np.zeros(self._dimension)

        # Preprocess
        tokens = self._tokenize(text)
        if not tokens:
            return np.zeros(self._dimension)

        # Generate n-gram features
        features = self._extract_features(tokens)

        # Hash features into fixed-dimension vector
        vector = self._hash_features(features)

        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            Array of shape (len(texts), dimension).
        """
        embeddings = [self.embed(text) for text in texts]
        return np.vstack(embeddings) if embeddings else np.zeros((0, self._dimension))

    def similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity between two texts.

        Args:
            text_a: First text.
            text_b: Second text.

        Returns:
            Cosine similarity score (0.0 to 1.0).
        """
        emb_a = self.embed(text_a)
        emb_b = self.embed(text_b)
        return float(np.dot(emb_a, emb_b))

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize and preprocess text.

        Steps:
        1. Lowercase
        2. Replace non-alphanumeric with spaces
        3. Split on whitespace
        4. Remove stopwords
        5. Remove very short tokens
        """
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s\-_/.]", " ", text)
        tokens = text.split()
        tokens = [t for t in tokens if t not in self._stopwords and len(t) > 1]
        return tokens

    def _extract_features(self, tokens: List[str]) -> Dict[str, float]:
        """Extract weighted n-gram features from tokens.

        Uses sublinear TF weighting: weight = 1 + log(count)
        This prevents very common words from dominating.
        """
        features: Dict[str, float] = {}

        # Unigrams
        for token in tokens:
            features[token] = features.get(token, 0) + 1.0

        # Bigrams (capture phrase-level meaning)
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}_{tokens[i + 1]}"
            features[bigram] = features.get(bigram, 0) + 1.0

        # Apply sublinear TF
        for key in features:
            if features[key] > 1:
                features[key] = 1.0 + math.log(features[key])

        return features

    def _hash_features(self, features: Dict[str, float]) -> np.ndarray:
        """Hash features into a fixed-dimension vector.

        Uses the hashing trick: each feature is mapped to a
        dimension via its hash, with the sign determined by a
        second hash. This gives us a fixed-size representation
        without needing a vocabulary.
        """
        vector = np.zeros(self._dimension)

        for feature, weight in features.items():
            # Primary hash → dimension index
            h1 = int(hashlib.md5(feature.encode()).hexdigest(), 16)
            idx = h1 % self._dimension

            # Secondary hash → sign (reduces collisions)
            h2 = int(hashlib.sha1(feature.encode()).hexdigest(), 16)
            sign = 1.0 if h2 % 2 == 0 else -1.0

            vector[idx] += sign * weight

        return vector

    def _build_stopwords(self) -> set:
        """Build a minimal stopword set."""
        return {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "shall",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "and",
            "but",
            "or",
            "nor",
            "not",
            "so",
            "yet",
            "both",
            "either",
            "neither",
            "each",
            "every",
            "all",
            "any",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "about",
            "also",
            "then",
            "that",
            "this",
            "these",
            "those",
            "it",
            "its",
            "i",
            "me",
            "my",
            "we",
            "our",
            "you",
            "your",
            "he",
            "him",
            "his",
            "she",
            "her",
            "they",
            "them",
            "their",
            "what",
            "which",
            "who",
            "whom",
            "when",
            "where",
            "why",
            "how",
            "if",
            "because",
            "while",
            "although",
            "though",
            "even",
            "still",
            "already",
        }
