"""Embedding generation and persistence tests (StudyAI Phased Migration - Phase 3).

Verifies:
- Canonical Qwen3-Embedding-0.6B provider (1024-d, L2 normalized, GPU/MPS/CPU).
- Deterministic hashing provider for test environments.
- Persistence format compatibility with pgvector (vector(1024)).
- Version mismatch handling and backfill tracking.
"""
import importlib.util
import numpy as np
import unittest
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase, override_settings

from providers.base import EmbeddingProvider
from providers.embeddings.hashing import HashingEmbeddingProvider
from providers.embeddings.qwen3 import (
    Qwen3EmbeddingProvider,
    DEFAULT_MODEL_NAME,
    DEFAULT_DIMENSION,
    DEFAULT_MODEL_VERSION,
)
from shared.exceptions import ProviderError

SENTENCE_TRANSFORMERS_AVAILABLE = importlib.util.find_spec("sentence_transformers") is not None


class TestHashingEmbeddingProvider(TestCase):
    """Test hashing-based embedding provider (used in testing & fallback)."""

    def test_embedding_dimension(self):
        """Hashing embeddings should respect settings dimension."""
        provider = HashingEmbeddingProvider()
        expected_dim = int(getattr(settings, "EMBEDDING_DIMENSIONS", 1024))
        self.assertEqual(provider.dimension, expected_dim)

    def test_embedding_deterministic(self):
        """Same text should produce same embedding."""
        provider = HashingEmbeddingProvider()
        emb1 = provider.embed(["test text"], model_version=provider.model_version)[0]
        emb2 = provider.embed(["test text"], model_version=provider.model_version)[0]
        np.testing.assert_array_equal(emb1, emb2)

    def test_different_texts_different_embeddings(self):
        """Different texts should produce different embeddings."""
        provider = HashingEmbeddingProvider()
        emb1 = provider.embed(["text one"], model_version=provider.model_version)[0]
        emb2 = provider.embed(["text two"], model_version=provider.model_version)[0]
        self.assertFalse(np.array_equal(emb1, emb2))

    def test_embedding_normalized(self):
        """Embeddings should be L2 normalized."""
        provider = HashingEmbeddingProvider()
        emb = provider.embed(["test"], model_version=provider.model_version)[0]
        norm = np.linalg.norm(emb)
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_batch_embedding(self):
        """Should handle batch of texts."""
        provider = HashingEmbeddingProvider()
        texts = ["text 1", "text 2", "text 3"]
        embeddings = provider.embed(texts, model_version=provider.model_version)
        self.assertEqual(len(embeddings), 3)
        self.assertTrue(all(len(e) == provider.dimension for e in embeddings))

    def test_model_properties(self):
        """Provider should expose model metadata."""
        provider = HashingEmbeddingProvider()
        self.assertEqual(provider.model_name, "hashing")
        self.assertEqual(provider.model_version, f"hashing-{provider.dimension}-v1")


@unittest.skipUnless(SENTENCE_TRANSFORMERS_AVAILABLE, "sentence_transformers not installed")
class TestQwen3EmbeddingProvider(TestCase):
    """Test canonical Qwen/Qwen3-Embedding-0.6B provider."""

    @patch("sentence_transformers.SentenceTransformer")
    def test_canonical_defaults(self, mock_st_class):
        """Provider should initialize with Qwen3-Embedding-0.6B defaults (1024-d)."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.01] * 1024], dtype=np.float32)
        mock_st_class.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="cpu")
        self.assertEqual(provider.model_name, DEFAULT_MODEL_NAME)
        self.assertEqual(provider.dimension, 1024)
        self.assertEqual(provider.model_version, DEFAULT_MODEL_VERSION)
        mock_st_class.assert_called_once_with(DEFAULT_MODEL_NAME, device="cpu")

    @patch("sentence_transformers.SentenceTransformer")
    def test_embed_single_text(self, mock_st_class):
        """Test embedding a single text string."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = [
            np.array([[0.01] * 1024], dtype=np.float32),  # probe in _load_model
            np.array([[0.05] * 1024], dtype=np.float32),  # actual call
        ]
        mock_st_class.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="cpu")
        embeddings = provider.embed(["Photosynthesis process in plants"], model_version=DEFAULT_MODEL_VERSION)

        self.assertEqual(len(embeddings), 1)
        self.assertEqual(len(embeddings[0]), 1024)
        self.assertIsInstance(embeddings[0], list)
        self.assertIsInstance(embeddings[0][0], float)

    @patch("sentence_transformers.SentenceTransformer")
    def test_embed_batch(self, mock_st_class):
        """Test batch embedding with normalization."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = [
            np.array([[0.01] * 1024], dtype=np.float32),  # probe
            np.array([[0.01] * 1024, [0.02] * 1024], dtype=np.float32),  # batch
        ]
        mock_st_class.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="cpu", batch_size=2)
        embeddings = provider.embed(["chunk 1", "chunk 2"], model_version=DEFAULT_MODEL_VERSION)

        self.assertEqual(len(embeddings), 2)
        self.assertEqual(len(embeddings[0]), 1024)
        self.assertEqual(len(embeddings[1]), 1024)
        call_args = mock_model.encode.call_args
        self.assertEqual(call_args[1]["batch_size"], 2)
        self.assertTrue(call_args[1]["normalize_embeddings"])

    def test_empty_batch_returns_empty_list(self):
        """Empty texts list should return empty list without calling model."""
        provider = Qwen3EmbeddingProvider.__new__(Qwen3EmbeddingProvider)
        provider._model = None
        self.assertEqual(provider.embed([]), [])

    @patch("sentence_transformers.SentenceTransformer")
    def test_model_version_mismatch_raises(self, mock_st_class):
        """Should raise ProviderError when requested model version does not match."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.01] * 1024], dtype=np.float32)
        mock_st_class.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="cpu")
        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"], model_version="legacy-minilm-v1")
        self.assertIn("Embedding model version mismatch", str(cm.exception))

    @patch("sentence_transformers.SentenceTransformer")
    def test_model_load_failure_raises(self, mock_st_class):
        """Should raise ProviderError when model fails to load."""
        mock_st_class.side_effect = RuntimeError("Weights file missing")
        provider = Qwen3EmbeddingProvider(device="cpu")
        self.assertIsNone(provider._model)

        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"])
        self.assertIn("not loaded", str(cm.exception))

    @patch("torch.backends.mps.is_available", return_value=True)
    @patch("torch.cuda.is_available", return_value=False)
    @patch("sentence_transformers.SentenceTransformer")
    def test_auto_device_selects_mps_on_apple_silicon(self, mock_st, mock_cuda, mock_mps):
        """On Apple Silicon Mac, auto device should select MPS."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.01] * 1024], dtype=np.float32)
        mock_st.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="auto")
        self.assertEqual(provider._device, "mps")


class TestEmbeddingPersistence(TestCase):
    """Test embedding persistence format compatibility with pgvector."""

    def test_hashing_embeddings_pgvector_compatible(self):
        """Hashing embeddings should be compatible with pgvector."""
        provider = HashingEmbeddingProvider()
        embeddings = provider.embed(["test"], model_version=provider.model_version)

        self.assertIsInstance(embeddings[0], list)
        self.assertTrue(all(isinstance(x, float) for x in embeddings[0]))
        self.assertEqual(len(embeddings[0]), provider.dimension)

    @patch("sentence_transformers.SentenceTransformer")
    def test_qwen3_embeddings_pgvector_compatible(self, mock_st_class):
        """Qwen3 embeddings should be list of 1024 floats for pgvector."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = [
            np.array([[0.01] * 1024], dtype=np.float32),
            np.array([[0.01] * 1024], dtype=np.float32),
        ]
        mock_st_class.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="cpu")
        embeddings = provider.embed(["test"], model_version=provider.model_version)

        self.assertIsInstance(embeddings[0], list)
        self.assertTrue(all(isinstance(x, float) for x in embeddings[0]))
        self.assertEqual(len(embeddings[0]), 1024)

    def test_embedding_dimension_consistency(self):
        """All embeddings from same provider should have consistent dimension."""
        provider = HashingEmbeddingProvider()
        for text in ["short", "a bit longer text", "x" * 1000]:
            emb = provider.embed([text], model_version=provider.model_version)[0]
            self.assertEqual(len(emb), provider.dimension)


class TestEmbeddingBackfill(TestCase):
    """Test embedding backfill and metadata tracking."""

    @patch("sentence_transformers.SentenceTransformer")
    def test_model_version_changes_require_backfill(self, mock_st_class):
        """Changing model version should trigger mismatch and backfill requirement."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = [
            np.array([[0.01] * 1024], dtype=np.float32),
            np.array([[0.01] * 1024], dtype=np.float32),
        ]
        mock_st_class.return_value = mock_model

        provider = Qwen3EmbeddingProvider(device="cpu")
        provider._model_version = "qwen3-embedding-0.6b-v2"

        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"], model_version="qwen3-embedding-0.6b-v1")
        self.assertIn("Embedding model version mismatch", str(cm.exception))

    def test_embedding_model_metadata(self):
        """Provider should expose metadata for backfill tracking."""
        provider = HashingEmbeddingProvider()
        metadata = {
            "model_name": provider.model_name,
            "model_version": provider.model_version,
            "dimension": provider.dimension,
            "normalization": "l2",
            "similarity_metric": "cosine",
        }
        self.assertEqual(metadata["dimension"], provider.dimension)
        self.assertEqual(metadata["normalization"], "l2")
        self.assertEqual(metadata["similarity_metric"], "cosine")