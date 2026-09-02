"""Provider registry: business logic asks for a provider by role (§24).

Provider selection is driven by environment variables:
- OCR_PROVIDER: "mock", "tesseract", "paddleocr" (default: "mock")
- LLM_PROVIDER: "mock", "ollama", "ollama-chat" (default: "mock")
- WEB_SEARCH_PROVIDER: "duckduckgo", "mock" (default: "duckduckgo")
- EMBEDDING_PROVIDER: "hashing", "sentence_transformers" (default: "hashing")
- STORAGE_BACKEND: "local", "minio", "s3" (default: "local")
- EMAIL_BACKEND: "mailpit", "smtp", "console" (default: "mailpit" for dev, "console" for tests)

Production providers (google, openai) are separate adapters that require credentials.
Local providers work without any external credentials.
"""
import os
from django.conf import settings

from providers.base import (
    EmbeddingProvider,
    LLMProvider,
    OCRProvider,
    ObjectStorageProvider,
    EmailProvider,
)
from providers.web.base import WebSearchProvider

# OCR
from providers.ocr.chain import OCRChainProvider
from providers.ocr.mock import MockOCRProvider

# LLM
from providers.llm.chain import LLMChainProvider
from providers.llm.mock import MockLLMProvider
from providers.llm.failing import FailingLLMProvider

# Web search
from providers.web.mock import MockWebSearchProvider

# Embeddings
from providers.embeddings.hashing import HashingEmbeddingProvider

# Storage
from providers.storage.local import LocalObjectStorage

# Email
from providers.email import MailpitEmailProvider, SMTPEmailProvider


def _get_env(name: str, default: str | None = None) -> str | None:
    """Get environment variable with Django settings fallback.
    
    Handles both string and list formats from settings.
    """
    value = getattr(settings, name, None) or os.environ.get(name, default)
    if isinstance(value, list):
        return ",".join(value)
    return value


# ============================================================================
# Object Storage
# ============================================================================

def get_object_storage() -> ObjectStorageProvider:
    """Get object storage provider based on STORAGE_BACKEND."""
    backend = _get_env("STORAGE_BACKEND", "local")
    
    if backend == "local":
        return LocalObjectStorage()
    
    if backend == "minio":
        from providers.storage.s3 import MinIOStorageProvider
        return MinIOStorageProvider(backend="minio")
    
    if backend == "s3":
        from providers.storage.s3 import S3StorageProvider
        if not _get_env("S3_ACCESS_KEY") or not _get_env("S3_SECRET_KEY"):
            raise ValueError("S3 backend requires S3_ACCESS_KEY and S3_SECRET_KEY environment variables")
        return S3StorageProvider(backend="s3")
    
    raise ValueError(f"Unknown STORAGE_BACKEND: {backend}")


# ============================================================================
# OCR
# ============================================================================

def _build_ocr(name: str):
    """Build single OCR provider by name."""
    if name == "mock":
        return MockOCRProvider()
    if name == "mock_low_confidence":
        return MockOCRProvider(confidence=0.42, name="mock_low_confidence")
    if name == "failing":
        return MockOCRProvider(fail=True, name="failing")
    if name == "tesseract":
        from providers.ocr.local import TesseractOCRProvider
        return TesseractOCRProvider()
    if name == "paddleocr":
        from providers.ocr.local import PaddleOCRProvider
        return PaddleOCRProvider()
    # Production providers (require credentials)
    if name == "google":
        try:
            from providers.ocr.google import GoogleVisionOCRProvider
        except ImportError:
            raise ValueError("Google Vision OCR provider not available (providers.ocr.google not implemented)")
        return GoogleVisionOCRProvider()
    raise ValueError(f"Unknown OCR provider: {name}")


def get_ocr_provider() -> OCRChainProvider:
    """Get OCR provider chain (primary + fallback).
    
    OCR_PROVIDER_CHAIN can be a comma-separated list: "tesseract,mock"
    Defaults to ["mock", "mock"] for backward compatibility.
    """
    chain_str = _get_env("OCR_PROVIDER_CHAIN", "mock,mock")
    names = [n.strip() for n in chain_str.split(",") if n.strip()]
    return OCRChainProvider([_build_ocr(n) for n in names])


# ============================================================================
# LLM
# ============================================================================

def _build_llm(name: str):
    """Build single LLM provider by name."""
    if name == "mock":
        return MockLLMProvider()
    if name == "failing":
        return FailingLLMProvider()
    if name == "ollama":
        from providers.llm.local import OllamaLLMProvider
        return OllamaLLMProvider()
    if name == "ollama-chat":
        from providers.llm.local import OllamaChatProvider
        return OllamaChatProvider()
    # Production providers (require credentials)
    if name == "openai":
        try:
            from providers.llm.openai import OpenAILLMProvider
        except ImportError:
            raise ValueError("OpenAI provider not available (providers.llm.openai not implemented)")
        if not _get_env("OPENAI_API_KEY"):
            raise ValueError("OpenAI provider requires OPENAI_API_KEY environment variable")
        return OpenAILLMProvider()
    if name == "anthropic":
        try:
            from providers.llm.anthropic import AnthropicLLMProvider
        except ImportError:
            raise ValueError("Anthropic provider not available (providers.llm.anthropic not implemented)")
        if not _get_env("ANTHROPIC_API_KEY"):
            raise ValueError("Anthropic provider requires ANTHROPIC_API_KEY environment variable")
        return AnthropicLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name}")


def get_llm_provider() -> LLMChainProvider:
    """Get LLM provider chain (primary + fallback).

    LLM_PROVIDER_CHAIN can be a comma-separated list: "ollama,mock"
    Defaults to ["mock", "mock"] for backward compatibility.
    """
    chain_str = _get_env("LLM_PROVIDER_CHAIN", "mock,mock")
    names = [n.strip() for n in chain_str.split(",") if n.strip()]
    return LLMChainProvider([_build_llm(n) for n in names])


# ============================================================================
# Web Search
# ============================================================================

def _build_web_search(name: str):
    """Build single web search provider by name."""
    if name == "mock":
        return MockWebSearchProvider()
    if name == "duckduckgo":
        from providers.web.duckduckgo import DuckDuckGoWebSearchProvider
        return DuckDuckGoWebSearchProvider()
    raise ValueError(f"Unknown web search provider: {name}")


def get_web_search_provider() -> WebSearchProvider:
    """Get web search provider.

    WEB_SEARCH_PROVIDER env var selects the provider.
    Defaults to "duckduckgo" (real web search, no API key).
    Use "mock" for deterministic tests.
    """
    name = _get_env("WEB_SEARCH_PROVIDER", "duckduckgo")
    return _build_web_search(name)


# ============================================================================
# Embeddings
# ============================================================================

def get_embedding_provider() -> EmbeddingProvider:
    """Get embedding provider based on EMBEDDING_PROVIDER."""
    name = _get_env("EMBEDDING_PROVIDER", "hashing")
    
    if name == "hashing":
        return HashingEmbeddingProvider()
    
    if name == "sentence_transformers":
        from providers.embeddings.local import SentenceTransformerEmbeddingProvider
        return SentenceTransformerEmbeddingProvider()
    
    # Production: same model but hosted
    if name == "openai":
        try:
            from providers.embeddings.openai import OpenAIEmbeddingProvider
        except ImportError:
            raise ValueError("OpenAI embeddings provider not available (providers.embeddings.openai not implemented)")
        if not _get_env("OPENAI_API_KEY"):
            raise ValueError("OpenAI embeddings require OPENAI_API_KEY")
        return OpenAIEmbeddingProvider()
    
    raise ValueError(f"Unknown embedding provider: {name}")


def embedding_model_version() -> str:
    """Get embedding model version for cache invalidation."""
    provider = _get_env("EMBEDDING_PROVIDER", "hashing")
    if provider == "sentence_transformers":
        model_name = _get_env("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        return f"{model_name.replace('/', '-')}-v1"
    return _get_env("EMBEDDING_MODEL_VERSION", "hashing-384-v1")


def embedding_dimension() -> int:
    """Get embedding dimension for the current provider."""
    provider = _get_env("EMBEDDING_PROVIDER", "hashing")
    if provider == "sentence_transformers":
        from providers.embeddings.local import SentenceTransformerEmbeddingProvider
        # Create temporary instance to get dimension
        p = SentenceTransformerEmbeddingProvider()
        return p.dimension
    return 384  # hashing default


# ============================================================================
# Email
# ============================================================================

def get_email_provider() -> EmailProvider:
    """Get email provider based on EMAIL_BACKEND."""
    backend = _get_env("EMAIL_BACKEND", "mailpit")
    
    if backend == "mailpit":
        return MailpitEmailProvider()
    
    if backend == "smtp":
        if not _get_env("SMTP_HOST"):
            raise ValueError("SMTP backend requires SMTP_HOST environment variable")
        return SMTPEmailProvider()
    
    if backend == "console":
        # Django's console backend - prints to stdout
        from django.core.mail import get_connection
        from providers.email import ConsoleEmailProvider
        return ConsoleEmailProvider()
    
    raise ValueError(f"Unknown EMAIL_BACKEND: {backend}")