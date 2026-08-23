"""Embedding generation and persistence tests (Phase 11)."""
import numpy as np
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from providers.embeddings.hashing import HashingEmbeddingProvider
from providers.embeddings.local import SentenceTransformerEmbeddingProvider
from providers.base import EmbeddingProvider


class TestHashingEmbeddingProvider(TestCase):
    """Test hashing-based embedding provider."""

    def test_embedding_dimension(self):
        """Hashing embeddings should have correct dimension."""
        provider = HashingEmbeddingProvider()
        assert provider.dimension == 384

    def test_embedding_deterministic(self):
        """Same text should produce same embedding."""
        provider = HashingEmbeddingProvider()
        
        emb1 = provider.embed(["test text"], model_version="hashing-384-v1")[0]
        emb2 = provider.embed(["test text"], model_version="hashing-384-v1")[0]
        
        np.testing.assert_array_equal(emb1, emb2)

    def test_different_texts_different_embeddings(self):
        """Different texts should produce different embeddings."""
        provider = HashingEmbeddingProvider()
        
        emb1 = provider.embed(["text one"], model_version="hashing-384-v1")[0]
        emb2 = provider.embed(["text two"], model_version="hashing-384-v1")[0]
        
        assert not np.array_equal(emb1, emb2)

    def test_embedding_normalized(self):
        """Embeddings should be L2 normalized."""
        provider = HashingEmbeddingProvider()
        
        emb = provider.embed(["test"], model_version="hashing-384-v1")[0]
        norm = np.linalg.norm(emb)
        
        assert abs(norm - 1.0) < 1e-5

    def test_batch_embedding(self):
        """Should handle batch of texts."""
        provider = HashingEmbeddingProvider()
        
        texts = ["text 1", "text 2", "text 3"]
        embeddings = provider.embed(texts, model_version="hashing-384-v1")
        
        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)

    def test_model_properties(self):
        """Provider should expose model metadata."""
        provider = HashingEmbeddingProvider()
        
        assert provider.model_name == "hashing"
        assert provider.model_version == "hashing-384-v1"


class TestSentenceTransformerEmbeddingProvider(TestCase):
    """Test sentence-transformers embedding provider."""

    @patch("sentence_transformers.SentenceTransformer")
    def test_provider_initialization(self, mock_st_class):
        """Test provider initializes model correctly."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384], dtype=np.float32)
        mock_st_class.return_value = mock_model
        
        provider = SentenceTransformerEmbeddingProvider(
            model_name="sentence-transformers/test-model",
            device="cpu"
        )
        
        assert provider.model_name == "sentence-transformers/test-model"
        assert provider.dimension == 384
        assert provider.model_version == "sentence-transformers-test-model-v1"
        mock_st_class.assert_called_once()

    @patch("sentence_transformers.SentenceTransformer")
    def test_embed_single_text(self, mock_st_class):
        """Test embedding single text."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5] * 384], dtype=np.float32)
        mock_st_class.return_value = mock_model
        
        provider = SentenceTransformerEmbeddingProvider()
        mock_model.reset_mock()  # Reset after init
        embeddings = provider.embed(["hello world"], model_version=provider.model_version)
        
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384
        mock_model.encode.assert_called_once()

    @patch("sentence_transformers.SentenceTransformer")
    def test_embed_batch(self, mock_st_class):
        """Test embedding batch of texts."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384], dtype=np.float32)
        mock_st_class.return_value = mock_model
        
        provider = SentenceTransformerEmbeddingProvider(batch_size=2)
        mock_model.reset_mock()  # Reset after init
        embeddings = provider.embed(["text 1", "text 2"], model_version=provider.model_version)
        
        assert len(embeddings) == 2
        mock_model.encode.assert_called_once()
        call_args = mock_model.encode.call_args
        assert call_args[1]["batch_size"] == 2
        assert call_args[1]["normalize_embeddings"] is True

    def test_model_version_mismatch_warning(self):
        """Should warn on model version mismatch."""
        from providers.embeddings.local import SentenceTransformerEmbeddingProvider
        provider = SentenceTransformerEmbeddingProvider()
        
        with self.assertLogs(level="WARNING") as cm:
            provider.embed(["test"], model_version="different-version")
        
        assert any("Model version mismatch" in msg for msg in cm.output)

    def test_missing_dependency_handled(self):
        """Should handle missing sentence-transformers gracefully."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            provider = SentenceTransformerEmbeddingProvider()
            assert provider._model is None
            
            with self.assertRaises(RuntimeError) as cm:
                provider.embed(["test"], model_version="v1")
            
            assert "not loaded" in str(cm.exception)


class TestEmbeddingPersistence(TestCase):
    """Test embedding persistence format compatibility."""

    def test_hashing_embeddings_pgvector_compatible(self):
        """Hashing embeddings should be compatible with pgvector."""
        provider = HashingEmbeddingProvider()
        embeddings = provider.embed(["test"], model_version="hashing-384-v1")
        
        # Should be list of floats (JSON serializable for pgvector)
        assert isinstance(embeddings[0], list)
        assert all(isinstance(x, float) for x in embeddings[0])
        assert len(embeddings[0]) == 384

    @patch("sentence_transformers.SentenceTransformer")
    def test_sentence_transformer_embeddings_pgvector_compatible(self, mock_st_class):
        """Sentence transformer embeddings should be compatible with pgvector."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384], dtype=np.float32)
        mock_st_class.return_value = mock_model
        
        provider = SentenceTransformerEmbeddingProvider()
        embeddings = provider.embed(["test"], model_version=provider.model_version)
        
        assert isinstance(embeddings[0], list)
        assert all(isinstance(x, float) for x in embeddings[0])
        assert len(embeddings[0]) == 384

    def test_embedding_dimension_consistency(self):
        """All embeddings from same provider should have same dimension."""
        provider = HashingEmbeddingProvider()
        
        for text in ["short", "a bit longer text", "x" * 1000]:
            emb = provider.embed([text], model_version="hashing-384-v1")[0]
            assert len(emb) == provider.dimension


class TestEmbeddingBackfill(TestCase):
    """Test embedding backfill requirements."""

    def test_model_version_changes_require_backfill(self):
        """Changing model version should indicate backfill needed."""
        provider_v1 = HashingEmbeddingProvider()
        # Manually change version to simulate model update
        provider_v1._model_version = "hashing-384-v2"
        
        # Embedding with old version should warn
        with self.assertLogs(level="WARNING") as cm:
            provider_v1.embed(["test"], model_version="hashing-384-v1")
        
        assert any("Model version mismatch" in msg for msg in cm.output)

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
        
        assert metadata["dimension"] == 384
        assert metadata["normalization"] == "l2"
        assert metadata["similarity_metric"] == "cosine"