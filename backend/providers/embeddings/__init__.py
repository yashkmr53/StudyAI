"""Embedding providers package."""
from providers.embeddings.local import SentenceTransformerEmbeddingProvider, HashingEmbeddingProvider
from providers.embeddings.hashing import HashingEmbeddingProvider as LegacyHashingProvider

__all__ = [
    "SentenceTransformerEmbeddingProvider",
    "HashingEmbeddingProvider",
    "LegacyHashingProvider",
]