"""Provider contract tests (Phase 11).

Tests that verify provider interfaces and selection work correctly.
"""
import os
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase, override_settings

from providers.base import (
    OCRProvider,
    LLMProvider,
    EmbeddingProvider,
    ObjectStorageProvider,
    EmailProvider,
    OCRResult,
    Prompt,
    StructuredLLMResult,
)
from providers.registry import (
    get_object_storage,
    get_ocr_provider,
    get_llm_provider,
    get_embedding_provider,
    get_email_provider,
    embedding_model_version,
    embedding_dimension,
)
from providers.ocr.mock import MockOCRProvider
from providers.llm.mock import MockLLMProvider
from providers.embeddings.hashing import HashingEmbeddingProvider
from providers.storage.local import LocalObjectStorage
from providers.email import ConsoleEmailProvider, MailpitEmailProvider, SMTPEmailProvider


class TestProviderContracts(TestCase):
    """Test that all providers implement the required protocols."""

    def test_mock_ocr_implements_protocol(self):
        provider = MockOCRProvider()
        assert isinstance(provider, OCRProvider)
        assert hasattr(provider, 'recognize')
        assert callable(provider.recognize)
        
        result = provider.recognize("test.jpg", request_id="req-123")
        assert isinstance(result, OCRResult)
        assert isinstance(result.lines, list)
        assert isinstance(result.confidence, float)
        assert isinstance(result.provider, str)

    def test_mock_llm_implements_protocol(self):
        provider = MockLLMProvider()
        assert isinstance(provider, LLMProvider)
        assert hasattr(provider, 'generate_structured')
        assert callable(provider.generate_structured)
        
        prompt = Prompt(name="test", version="v1", user="test")
        result = provider.generate_structured(prompt=prompt, schema=dict, request_id="req-123")
        assert isinstance(result, StructuredLLMResult)
        assert isinstance(result.data, dict)
        assert isinstance(result.model, str)

    def test_hashing_embedding_implements_protocol(self):
        provider = HashingEmbeddingProvider()
        assert isinstance(provider, EmbeddingProvider)
        assert hasattr(provider, 'embed')
        assert callable(provider.embed)
        assert hasattr(provider, 'dimension')
        assert hasattr(provider, 'model_name')
        assert hasattr(provider, 'model_version')
        
        embeddings = provider.embed(["test"], model_version="hashing-384-v1")
        assert isinstance(embeddings, list)
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384

    def test_local_storage_implements_protocol(self):
        provider = LocalObjectStorage()
        assert isinstance(provider, ObjectStorageProvider)
        assert hasattr(provider, 'create_upload_url')
        assert hasattr(provider, 'create_download_url')
        assert hasattr(provider, 'delete')
        assert hasattr(provider, 'store_bytes')
        assert hasattr(provider, 'read_bytes')
        assert hasattr(provider, 'exists')
        assert hasattr(provider, 'size')

    def test_console_email_implements_protocol(self):
        provider = ConsoleEmailProvider()
        assert isinstance(provider, EmailProvider)
        assert hasattr(provider, 'send_email')
        assert hasattr(provider, 'send_password_reset_email')
        assert callable(provider.send_email)
        assert callable(provider.send_password_reset_email)


class TestProviderSelection(TestCase):
    """Test provider selection via environment variables."""

    @override_settings(STORAGE_BACKEND="local")
    def test_get_object_storage_local(self):
        storage = get_object_storage()
        assert isinstance(storage, LocalObjectStorage)

    @override_settings(STORAGE_BACKEND="minio")
    @patch("providers.registry.MinioStorageProvider")
    def test_get_object_storage_minio(self, mock_minio):
        mock_instance = MagicMock()
        mock_minio.return_value = mock_instance
        
        storage = get_object_storage()
        assert storage is mock_instance
        mock_minio.assert_called_once_with(backend="minio")

    @override_settings(STORAGE_BACKEND="s3", S3_ACCESS_KEY="test", S3_SECRET_KEY="test")
    @patch("providers.registry.S3StorageProvider")
    def test_get_object_storage_s3(self, mock_s3):
        mock_instance = MagicMock()
        mock_s3.return_value = mock_instance
        
        storage = get_object_storage()
        assert storage is mock_instance

    @override_settings(STORAGE_BACKEND="invalid")
    def test_get_object_storage_invalid(self):
        with self.assertRaises(ValueError):
            get_object_storage()

    @override_settings(OCR_PROVIDER_CHAIN="mock,mock")
    def test_get_ocr_provider_mock_chain(self):
        provider = get_ocr_provider()
        assert isinstance(provider, OCRChainProvider)
        assert len(provider.providers) == 2
        assert all(isinstance(p, MockOCRProvider) for p in provider.providers)

    @override_settings(OCR_PROVIDER_CHAIN="tesseract,mock")
    @patch("providers.registry.TesseractOCRProvider")
    def test_get_ocr_provider_tesseract(self, mock_tesseract):
        mock_instance = MagicMock()
        mock_tesseract.return_value = mock_instance
        
        provider = get_ocr_provider()
        assert isinstance(provider, OCRChainProvider)
        assert len(provider.providers) == 2

    @override_settings(LLM_PROVIDER_CHAIN="mock,mock")
    def test_get_llm_provider_mock_chain(self):
        provider = get_llm_provider()
        assert isinstance(provider, LLMChainProvider)
        assert len(provider.providers) == 2
        assert all(isinstance(p, MockLLMProvider) for p in provider.providers)

    @override_settings(LLM_PROVIDER_CHAIN="ollama,mock")
    @patch("providers.llm.local.OllamaLLMProvider")
    def test_get_llm_provider_ollama(self, mock_ollama):
        mock_instance = MagicMock()
        mock_ollama.return_value = mock_instance
        
        provider = get_llm_provider()
        assert isinstance(provider, LLMChainProvider)
        assert len(provider.providers) == 2

    @override_settings(EMBEDDING_PROVIDER="hashing")
    def test_get_embedding_provider_hashing(self):
        provider = get_embedding_provider()
        assert isinstance(provider, HashingEmbeddingProvider)

    @override_settings(EMBEDDING_PROVIDER="sentence_transformers")
    @patch("providers.embeddings.local.SentenceTransformerEmbeddingProvider")
    def test_get_embedding_provider_sentence_transformers(self, mock_st):
        mock_instance = MagicMock()
        mock_st.return_value = mock_instance
        
        provider = get_embedding_provider()
        assert provider is mock_instance

    @override_settings(EMAIL_BACKEND="console")
    def test_get_email_provider_console(self):
        provider = get_email_provider()
        assert isinstance(provider, ConsoleEmailProvider)

    @override_settings(EMAIL_BACKEND="mailpit")
    def test_get_email_provider_mailpit(self):
        provider = get_email_provider()
        assert isinstance(provider, MailpitEmailProvider)

    @override_settings(EMAIL_BACKEND="smtp", SMTP_HOST="smtp.example.com")
    def test_get_email_provider_smtp(self):
        provider = get_email_provider()
        assert isinstance(provider, SMTPEmailProvider)

    @override_settings(EMAIL_BACKEND="smtp")
    def test_get_email_provider_smtp_missing_host(self):
        with self.assertRaises(ValueError):
            get_email_provider()

    def test_embedding_model_version(self):
        with override_settings(EMBEDDING_PROVIDER="hashing", EMBEDDING_MODEL_VERSION="test-v1"):
            version = embedding_model_version()
            assert version == "test-v1"
        
        with override_settings(EMBEDDING_PROVIDER="sentence_transformers", 
                              EMBEDDING_MODEL_NAME="sentence-transformers/test-model"):
            version = embedding_model_version()
            assert version == "sentence-transformers-test-model-v1"

    def test_embedding_dimension(self):
        with override_settings(EMBEDDING_PROVIDER="hashing"):
            dim = embedding_dimension()
            assert dim == 384


class TestLocalProviderStartup(TestCase):
    """Test that local providers can start without cloud credentials."""

    def test_mock_ocr_no_credentials_needed(self):
        provider = MockOCRProvider()
        result = provider.recognize("test.jpg", request_id="req-1")
        assert result.provider == "mock"

    def test_hashing_embedding_no_credentials_needed(self):
        provider = HashingEmbeddingProvider()
        embeddings = provider.embed(["test"], model_version="hashing-384-v1")
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384

    def test_local_storage_no_credentials_needed(self):
        provider = LocalObjectStorage()
        # Should work without any external credentials
        url = provider.create_upload_url("test.txt", content_type="text/plain", ttl_seconds=300)
        assert "token=" in url

    def test_console_email_no_credentials_needed(self):
        provider = ConsoleEmailProvider()
        provider.send_email(
            to=["test@example.com"],
            subject="Test",
            body_text="Hello",
        )
        emails = provider.get_sent_emails()
        assert len(emails) == 1
        assert emails[0]["to"] == ["test@example.com"]


class TestInvalidProviderConfiguration(TestCase):
    """Test handling of invalid provider configurations."""

    @override_settings(STORAGE_BACKEND="invalid_backend")
    def test_invalid_storage_backend(self):
        with self.assertRaises(ValueError) as cm:
            get_object_storage()
        assert "Unknown STORAGE_BACKEND" in str(cm.exception)

    @override_settings(OCR_PROVIDER_CHAIN="nonexistent")
    def test_invalid_ocr_provider(self):
        with self.assertRaises(ValueError) as cm:
            get_ocr_provider()
        assert "Unknown OCR provider" in str(cm.exception)

    @override_settings(LLM_PROVIDER_CHAIN="nonexistent")
    def test_invalid_llm_provider(self):
        with self.assertRaises(ValueError) as cm:
            get_llm_provider()
        assert "Unknown LLM provider" in str(cm.exception)

    @override_settings(EMBEDDING_PROVIDER="nonexistent")
    def test_invalid_embedding_provider(self):
        with self.assertRaises(ValueError) as cm:
            get_embedding_provider()
        assert "Unknown embedding provider" in str(cm.exception)

    @override_settings(EMAIL_BACKEND="nonexistent")
    def test_invalid_email_backend(self):
        with self.assertRaises(ValueError) as cm:
            get_email_provider()
        assert "Unknown EMAIL_BACKEND" in str(cm.exception)

    @override_settings(STORAGE_BACKEND="s3")  # Missing credentials
    def test_s3_missing_credentials(self):
        with self.assertRaises(ValueError) as cm:
            get_object_storage()
        assert "S3_ACCESS_KEY" in str(cm.exception) or "S3_SECRET_KEY" in str(cm.exception)

    @override_settings(LLM_PROVIDER_CHAIN="openai")  # Missing API key
    def test_openai_missing_credentials(self):
        with self.assertRaises(ValueError) as cm:
            get_llm_provider()
        # Provider not implemented, so error is about missing implementation
        assert "OpenAI provider not available" in str(cm.exception) or "OPENAI_API_KEY" in str(cm.exception)


class TestProviderSwitching(TestCase):
    """Test that switching providers doesn't require business logic changes."""

    @override_settings(
        STORAGE_BACKEND="local",
        OCR_PROVIDER_CHAIN="mock,mock",
        LLM_PROVIDER_CHAIN="mock,mock",
        EMBEDDING_PROVIDER="hashing",
        EMAIL_BACKEND="console",
    )
    def test_all_local_providers_work_together(self):
        """All local providers should work together without cloud credentials."""
        storage = get_object_storage()
        ocr = get_ocr_provider()
        llm = get_llm_provider()
        embedding = get_embedding_provider()
        email = get_email_provider()
        
        assert isinstance(storage, LocalObjectStorage)
        assert isinstance(ocr, OCRChainProvider)
        assert isinstance(llm, LLMChainProvider)
        assert isinstance(embedding, HashingEmbeddingProvider)
        assert isinstance(email, ConsoleEmailProvider)

    @override_settings(
        STORAGE_BACKEND="minio",
        OCR_PROVIDER_CHAIN="tesseract,mock",
        LLM_PROVIDER_CHAIN="ollama,mock",
        EMBEDDING_PROVIDER="sentence_transformers",
        EMAIL_BACKEND="mailpit",
        MINIO_ACCESS_KEY="test",
        MINIO_SECRET_KEY="test",
    )
    @patch("providers.storage.s3.MinIOStorageProvider")
    @patch("providers.ocr.local.TesseractOCRProvider")
    @patch("providers.llm.local.OllamaLLMProvider")
    @patch("providers.embeddings.local.SentenceTransformerEmbeddingProvider")
    def test_all_development_providers(
        self, mock_st, mock_ollama, mock_tesseract, mock_minio
    ):
        """All development providers should work together."""
        for mock in [mock_st, mock_ollama, mock_tesseract, mock_minio]:
            mock.return_value = MagicMock()
        
        storage = get_object_storage()
        ocr = get_ocr_provider()
        llm = get_llm_provider()
        embedding = get_embedding_provider()
        email = get_email_provider()
        
        # All should be instantiated without errors
        assert storage is not None
        assert ocr is not None
        assert llm is not None
        assert embedding is not None
        assert email is not None


# Import chain providers for type checking
from providers.ocr.chain import OCRChainProvider
from providers.llm.chain import LLMChainProvider