"""Ollama Embedding Provider (GPU/MPS accelerated via host Ollama).

Generates dense embeddings using Ollama's /api/embed endpoint.
Runs locally on macOS host with Apple Silicon Metal/MPS GPU hardware acceleration.

Default model: qwen3-embedding:0.6b (1024 dimensions, multilingual, 32k context)
Compatible with pgvector vector(1024) and StudyAI retrieval pipeline.
"""
import logging
import os
from typing import Optional

import numpy as np
import requests

from providers.base import EmbeddingProvider
from shared.exceptions import ProviderError

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "qwen3-embedding:0.6b"
DEFAULT_DIMENSION = 1024
DEFAULT_MODEL_VERSION = "qwen3-embedding-0.6b-v1"
DEFAULT_BATCH_SIZE = 32


class OllamaEmbeddingProvider:
    """Ollama embedding provider leveraging native GPU/Metal on the host."""

    name = "ollama"

    def __init__(
        self,
        *,
        model_name: Optional[str] = None,
        dimension: int = DEFAULT_DIMENSION,
        base_url: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        model_version: Optional[str] = None,
        timeout: int = 60,
    ):
        dj = self._get_django_settings()
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or getattr(dj, "OLLAMA_BASE_URL", "http://localhost:11434")
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
            or os.environ.get("EMBEDDING_MODEL_VERSION")
            or getattr(dj, "EMBEDDING_MODEL_VERSION", DEFAULT_MODEL_VERSION)
        )
        self.batch_size = batch_size
        self.timeout = timeout

        self.session = requests.Session()

        logger.info(
            "OllamaEmbeddingProvider initialized (base_url=%s, model=%s, dim=%d, version=%s)",
            self.base_url,
            self._model_name,
            self._dimension,
            self._model_version,
        )

    @staticmethod
    def _get_django_settings():
        try:
            from django.conf import settings
            return settings
        except Exception:
            return None

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
        """Generate normalized dense vectors for texts via Ollama embed endpoint."""
        if not texts:
            return []

        if model_version and model_version != self._model_version:
            raise ProviderError(
                f"Embedding model version mismatch: requested={model_version}, provider={self._model_version}"
            )

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            payload = {
                "model": self._model_name,
                "input": batch,
            }
            try:
                resp = self.session.post(
                    f"{self.base_url}/api/embed",
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code == 404:
                    raise ProviderError(
                        f"Model '{self._model_name}' not found in Ollama at {self.base_url}. "
                        f"Please run 'ollama pull {self._model_name}' on the host."
                    )
                resp.raise_for_status()
                data = resp.json()
                raw_embs = data.get("embeddings", [])
                if not raw_embs:
                    raise ProviderError(f"Ollama returned no embeddings in response: {data}")

                # Ensure L2 normalization and validate dimension
                for vec in raw_embs:
                    arr = np.array(vec, dtype=np.float32)
                    if len(arr) != self._dimension:
                        raise ProviderError(
                            f"Embedding dimension mismatch: expected {self._dimension}, got {len(arr)}"
                        )
                    norm = np.linalg.norm(arr)
                    if norm > 0:
                        arr = arr / norm
                    all_embeddings.append(arr.tolist())

            except requests.ConnectionError as exc:
                logger.exception("Failed to connect to Ollama at %s: %s", self.base_url, exc)
                raise ProviderError(f"Cannot connect to Ollama embed endpoint at {self.base_url}: {exc}") from exc
            except requests.RequestException as exc:
                logger.exception("Ollama embedding HTTP error at %s: %s", self.base_url, exc)
                raise ProviderError(f"Ollama embedding request failed: {exc}") from exc
            except ProviderError:
                raise
            except Exception as exc:
                logger.exception("Ollama embedding generation error: %s", exc)
                raise ProviderError(f"Ollama embedding error: {exc}") from exc

        return all_embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        res = self.embed([text])
        return res[0] if res else []
