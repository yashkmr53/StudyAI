"""Embedding providers package."""
from providers.embeddings.ollama import OllamaEmbeddingProvider
from providers.embeddings.qwen3 import Qwen3EmbeddingProvider
from providers.embeddings.local import SentenceTransformerEmbeddingProvider, HashingEmbeddingProvider
from providers.embeddings.hashing import HashingEmbeddingProvider as LegacyHashingProvider

__all__ = [
    "OllamaEmbeddingProvider",
    "Qwen3EmbeddingProvider",
    "SentenceTransformerEmbeddingProvider",
    "HashingEmbeddingProvider",
    "LegacyHashingProvider",
]