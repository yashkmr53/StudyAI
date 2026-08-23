"""Local sentence-transformers embedding provider (Phase 11).

Generates embeddings using sentence-transformers models locally.
Default model: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)

Model characteristics:
- Vector dimension: 384
- Model name: sentence-transformers/all-MiniLM-L6-v2
- Normalization: L2 normalized (cosine similarity = dot product)
- Similarity metric: Cosine similarity (dot product on normalized vectors)
- Persistence format: Float32 arrays in pgvector
- Backfill requirements: Full re-embedding required on model change
"""
import logging
import os
from typing import Optional

import numpy as np

from providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class SentenceTransformerEmbeddingProvider:
    """Local sentence-transformers embedding provider.
    
    Runs entirely locally using the sentence-transformers library.
    No external API calls or credentials required.
    
    Environment variables:
        EMBEDDING_MODEL_NAME: Model identifier (default: sentence-transformers/all-MiniLM-L6-v2)
        EMBEDDING_DEVICE: Device to run on - cpu, cuda, mps (default: auto-detect)
        EMBEDDING_BATCH_SIZE: Batch size for encoding (default: 32)
    
    Model properties:
        - dimension: 384 (for all-MiniLM-L6-v2)
        - model_name: The HF model identifier
        - model_version: Version string for cache invalidation
        - normalization: L2 normalized vectors
        - similarity: Cosine similarity (dot product on normalized)
    """
    
    def __init__(
        self,
        *,
        model_name: str | None = None,
        device: str | None = None,
        batch_size: int = 32,
        fail: bool = False,
        name: str = "sentence_transformers",
    ):
        self.name = name
        self.fail = fail
        self.batch_size = batch_size
        
        self.model_name = model_name or os.environ.get(
            "EMBEDDING_MODEL_NAME",
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.device = device or os.environ.get("EMBEDDING_DEVICE", "auto")
        
        self._model: Optional[Any] = None
        self._dimension: int = 384
        self._model_version: str = "all-MiniLM-L6-v2-v1"
        
        self._load_model()
        logger.info(
            "SentenceTransformer embedding initialized "
            "(model=%s, dimension=%d, version=%s, device=%s)",
            self.model_name, self.dimension, self.model_version, self._device
        )
    
    def _load_model(self) -> None:
        """Load the sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer
            import torch
            
            # Determine device
            if self.device == "auto":
                if torch.cuda.is_available():
                    self._device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._device = "mps"
                else:
                    self._device = "cpu"
            else:
                self._device = self.device
            
            self._model = SentenceTransformer(self.model_name, device=self._device)
            
            # Verify dimension
            test_embedding = self._model.encode(["test"], normalize_embeddings=True)
            self._dimension = test_embedding.shape[1]
            
            # Create version string from model name
            self._model_version = f"{self.model_name.replace('/', '-')}-v1"
            
        except ImportError:
            logger.warning("sentence-transformers not installed; provider will not work")
            self._model = None
        except Exception as e:
            logger.exception("Failed to load sentence-transformers model")
            self._model = None
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @model_name.setter
    def model_name(self, value: str):
        self._model_name = value
    
    @property
    def model_version(self) -> str:
        return self._model_version
    
    def embed(self, texts: list[str], *, model_version: str) -> list[list[float]]:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            model_version: Expected model version (for cache validation)
            
        Returns:
            List of embedding vectors (L2 normalized)
            
        Raises:
            RuntimeError: If model not loaded or version mismatch
        """
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        if self._model is None:
            raise RuntimeError("SentenceTransformer model not loaded (sentence-transformers not installed?)")
        
        if model_version != self._model_version:
            logger.warning(
                "Model version mismatch: expected %s, got %s. "
                "This may indicate a model change requiring re-embedding.",
                self._model_version, model_version
            )
        
        try:
            # Encode in batches
            embeddings = self._model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,  # L2 normalize for cosine similarity
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            
            # Convert to list of lists
            return embeddings.astype(np.float32).tolist()
            
        except Exception as e:
            logger.exception("Embedding generation failed")
            raise RuntimeError(f"Embedding generation failed: {e}") from e
    
    def embed_single(self, text: str, *, model_version: str) -> list[float]:
        """Generate embedding for a single text."""
        return self.embed([text], model_version=model_version)[0]


class HashingEmbeddingProvider:
    """Fallback hashing-based embedding provider (existing).
    
    Deterministic, no ML dependencies. Lower quality but always works.
    Kept for backward compatibility and testing.
    """
    
    name = "hashing"
    dimension = 384
    model_name = "hashing"
    model_version = "hashing-384-v1"
    
    def __init__(self, *, fail: bool = False, name: str = "hashing"):
        self.name = name
        self.fail = fail
    
    def embed(self, texts: list[str], *, model_version: str) -> list[list[float]]:
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        import hashlib
        embeddings = []
        for text in texts:
            # Deterministic hash-based embedding
            hash_obj = hashlib.shake_256(text.encode())
            # Generate 384-dim vector from hash
            vector = [int.from_bytes(hash_obj.digest(4), "little") / 2**32 - 0.5 for _ in range(384)]
            # Normalize
            norm = sum(x * x for x in vector) ** 0.5
            if norm > 0:
                vector = [x / norm for x in vector]
            embeddings.append(vector)
        return embeddings