"""Canonical Qwen3-Embedding-0.6B Provider (StudyAI Phased Migration).

Generates dense embeddings using Qwen/Qwen3-Embedding-0.6B.
Runs locally with GPU acceleration (MPS on Apple Silicon, CUDA, or CPU fallback).

Model Characteristics:
- Model: Qwen/Qwen3-Embedding-0.6B
- Vector dimension: 1024
- Normalization: L2 normalized (cosine similarity = dot product)
- Similarity metric: Cosine distance (pgvector vector_cosine_ops)
- Context length: Up to 32,768 tokens
"""
import logging
import os
from typing import Optional, Union

import numpy as np

from providers.base import EmbeddingProvider
from shared.exceptions import ProviderError

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_DIMENSION = 1024
DEFAULT_MODEL_VERSION = "qwen3-embedding-0.6b-v1"


class Qwen3EmbeddingProvider:
    """Canonical embedding provider for StudyAI using Qwen/Qwen3-Embedding-0.6B."""

    name = "sentence_transformers"

    def __init__(
        self,
        *,
        model_name: Optional[str] = None,
        dimension: int = DEFAULT_DIMENSION,
        device: Optional[str] = None,
        batch_size: int = 32,
        model_version: Optional[str] = None,
    ):
        dj = self._get_django_settings()
        dj_provider = getattr(dj, "EMBEDDING_PROVIDER", None)
        env_provider = os.environ.get("EMBEDDING_PROVIDER")
        is_qwen_provider = (env_provider or dj_provider) in (
            None, "sentence_transformers", "qwen3", "qwen", "qwen3-embedding"
        )
        dj_version = (
            getattr(dj, "EMBEDDING_MODEL_VERSION", None)
            if is_qwen_provider
            else None
        )
        env_version = (
            os.environ.get("EMBEDDING_MODEL_VERSION")
            if is_qwen_provider
            else None
        )
        self._model_name = (
            model_name
            or os.environ.get("EMBEDDING_MODEL_NAME")
            or getattr(dj, "EMBEDDING_MODEL_NAME", DEFAULT_MODEL_NAME)
        )
        self._dimension = int(
            os.environ.get("EMBEDDING_DIMENSIONS")
            or getattr(dj, "EMBEDDING_DIMENSIONS", dimension)
        )
        self._model_version = (
            model_version
            or env_version
            or dj_version
            or DEFAULT_MODEL_VERSION
        )
        self.device_setting = (
            device
            or os.environ.get("EMBEDDING_DEVICE")
            or getattr(dj, "EMBEDDING_DEVICE", "auto")
        )
        self.batch_size = batch_size
        self._device = "cpu"
        self._model = None

        self._load_model()
        logger.info(
            "Qwen3EmbeddingProvider initialized (model=%s, dim=%d, version=%s, device=%s)",
            self._model_name,
            self._dimension,
            self._model_version,
            self._device,
        )

    @staticmethod
    def _get_django_settings():
        try:
            from django.conf import settings
            return settings
        except Exception:
            return None

    def _load_model(self) -> None:
        """Load the SentenceTransformer model on the target compute device."""
        try:
            import torch
            from sentence_transformers import SentenceTransformer

            if self.device_setting == "auto":
                if torch.cuda.is_available():
                    self._device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._device = "mps"
                else:
                    self._device = "cpu"
            else:
                self._device = self.device_setting

            self._model = SentenceTransformer(self._model_name, device=self._device)
            # Verify dimension
            test_vec = self._model.encode(["probe"], normalize_embeddings=True)
            self._dimension = int(test_vec.shape[1])
        except Exception as exc:
            logger.warning(
                "Could not load SentenceTransformer '%s' on %s: %s",
                self._model_name,
                self.device_setting,
                exc,
            )

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    def embed(self, texts: list[str], *, model_version: Optional[str] = None) -> list[list[float]]:
        """Generate normalized 1024-dimensional dense vectors for texts."""
        if not texts:
            return []

        if model_version and model_version != self._model_version:
            raise ProviderError(
                f"Embedding model version mismatch: requested={model_version}, provider={self._model_version}"
            )

        if self._model is None:
            self._load_model()
            if self._model is None:
                raise ProviderError(
                    f"Embedding model {self._model_name} is not loaded on device {self._device}"
                )

        try:
            embeddings = self._model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            if isinstance(embeddings, np.ndarray):
                return embeddings.tolist()
            return [list(vec) for vec in embeddings]
        except Exception as exc:
            logger.exception("Failed to generate embeddings for batch: %s", exc)
            raise ProviderError(f"Embedding generation failed: {exc}") from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Convenience alias matching LangChain interface."""
        return self.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        """Convenience alias matching LangChain interface."""
        res = self.embed([text])
        return res[0] if res else []
