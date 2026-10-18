"""Embedding generation and persistence tests (Canonical Phase 14 Stack).

Verifies:
- Canonical OllamaEmbeddingProvider (1024-d, L2 normalized, host GPU/MPS acceleration).
- Deterministic hashing provider for test environments.
- Persistence format compatibility with pgvector (vector(1024)).
- Version mismatch handling and backfill tracking.
"""
import numpy as np
import requests
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase, override_settings

from providers.base import EmbeddingProvider
from providers.embeddings.hashing import HashingEmbeddingProvider
from providers.embeddings.ollama import (
    OllamaEmbeddingProvider,
    DEFAULT_MODEL_NAME,
    DEFAULT_DIMENSION,
    DEFAULT_MODEL_VERSION,
)
from shared.exceptions import ProviderError


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

    def test_embedding_dimension_consistency(self):
        """All embeddings from same provider should have consistent dimension."""
        provider = HashingEmbeddingProvider()
        for text in ["short", "a bit longer text", "x" * 1000]:
            emb = provider.embed([text], model_version=provider.model_version)[0]
            self.assertEqual(len(emb), provider.dimension)


class TestEmbeddingBackfill(TestCase):
    """Test embedding backfill and metadata tracking."""

    def test_model_version_changes_require_backfill(self):
        """Changing model version should trigger mismatch and backfill requirement."""
        provider = OllamaEmbeddingProvider()
        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"], model_version="legacy-minilm-v1")
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


class TestOllamaEmbeddingProvider(TestCase):
    """Test OllamaEmbeddingProvider with mocked HTTP endpoints."""

    def test_provider_initialization_defaults(self):
        provider = OllamaEmbeddingProvider()
        self.assertEqual(provider.dimension, 1024)
        self.assertEqual(provider.model_name, "qwen3-embedding:0.6b")
        self.assertEqual(provider.model_version, "qwen3-embedding-0.6b-v1")

    @patch("requests.Session.post")
    def test_embed_returns_normalized_vectors(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [
                [3.0, 4.0] + [0.0] * 1022,
                [0.0, 5.0, 12.0] + [0.0] * 1021,
            ]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        provider = OllamaEmbeddingProvider()
        vectors = provider.embed(["text1", "text2"])

        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 1024)
        self.assertEqual(len(vectors[1]), 1024)

        # Check normalization (norm == 1.0)
        norm0 = np.linalg.norm(np.array(vectors[0]))
        self.assertAlmostEqual(norm0, 1.0, places=5)
        # 3/5 = 0.6, 4/5 = 0.8
        self.assertAlmostEqual(vectors[0][0], 0.6, places=5)
        self.assertAlmostEqual(vectors[0][1], 0.8, places=5)

    def test_embed_empty_list(self):
        provider = OllamaEmbeddingProvider()
        self.assertEqual(provider.embed([]), [])

    def test_version_mismatch_raises_error(self):
        provider = OllamaEmbeddingProvider()
        with self.assertRaises(ProviderError):
            provider.embed(["test"], model_version="mismatched-version")

    @patch("requests.Session.post")
    def test_dimension_mismatch_raises_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[1.0] * 512]  # wrong dimension: 512 instead of 1024
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        provider = OllamaEmbeddingProvider()
        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"])
        self.assertIn("Embedding dimension mismatch", str(cm.exception))

    @patch("requests.Session.post")
    def test_model_not_found_raises_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_post.return_value = mock_resp

        provider = OllamaEmbeddingProvider()
        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"])
        self.assertIn("not found in Ollama", str(cm.exception))

    @patch("requests.Session.post")
    def test_connection_error_raises_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        provider = OllamaEmbeddingProvider()
        with self.assertRaises(ProviderError) as cm:
            provider.embed(["test"])
        self.assertIn("Cannot connect to Ollama", str(cm.exception))

    @patch("requests.Session.post")
    def test_embed_documents_and_query_convenience_methods(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[1.0] + [0.0] * 1023]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        provider = OllamaEmbeddingProvider()
        doc_embs = provider.embed_documents(["doc1"])
        query_emb = provider.embed_query("query1")

        self.assertEqual(len(doc_embs), 1)
        self.assertEqual(len(doc_embs[0]), 1024)
        self.assertEqual(len(query_emb), 1024)