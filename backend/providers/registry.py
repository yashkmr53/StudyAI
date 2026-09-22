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
from typing import Optional

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


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with Django settings fallback.
    
    Handles both string and list formats from settings.
    """
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(name, default)
    if isinstance(value, list):
        return ",".join(value)
    return value


# ============================================================================
# Object Storage
# ============================================================================

def get_object_storage() -> ObjectStorageProvider:
    """Get object storage provider based on STORAGE_BACKEND / OBJECT_STORAGE_BACKEND."""
    backend = getattr(settings, "STORAGE_BACKEND", None)
    if not backend:
        backend = getattr(settings, "OBJECT_STORAGE_BACKEND", None)
    if not backend:
        backend = os.environ.get("STORAGE_BACKEND", "local")
    
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
    """Build single OCR provider by name.

    The StudyAI production AI stack uses qwen3.5:4b for handwritten note OCR.
    Legacy local OCR engines (Tesseract, PaddleOCR) and hosted vision APIs
    are superseded by native multimodal qwen3.5:4b.
    """
    if name in ("qwen35", "qwen3.5", "qwen3.5:4b", "ollama"):
        from providers.ocr.qwen35 import Qwen35OCRProvider
        return Qwen35OCRProvider()
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

    OCR_PROVIDER_CHAIN can be a comma-separated list: "qwen35" or "qwen35,mock"
    Defaults to "qwen35" in production, or "mock,mock" in unit tests.
    """
    chain_str = _get_env("OCR_PROVIDER_CHAIN", "qwen35")
    names = [n.strip() for n in chain_str.split(",") if n.strip()]
    providers = [_build_ocr(n) for n in names]

    is_qwen35 = bool(providers and getattr(providers[0], "name", "") in ("qwen35", "ollama"))
    disable_fallback = _flag("LLM_DISABLE_FALLBACK", default="true" if is_qwen35 else "false")
    return OCRChainProvider(providers, disable_fallback=disable_fallback)


# ============================================================================
# LLM
# ============================================================================

def _build_llm(name: str):
    """Build single LLM provider by name.
    
    The StudyAI production AI stack uses qwen3.5:4b via Ollama.
    Legacy hosted providers (OpenAI, Anthropic) are removed from the production path.
    """
    if name == "mock":
        return MockLLMProvider()
    if name == "failing":
        return FailingLLMProvider()
    if name in ("ollama", "qwen35", "qwen", "qwen3.5:4b", "ollama-chat"):
        from providers.llm.qwen35 import Qwen35Provider
        return Qwen35Provider()
    if name == "openai":
        raise ValueError("OpenAI provider not available (legacy hosted provider removed in favor of qwen3.5:4b)")
    raise ValueError(
        f"Unknown LLM provider: {name}. Production stack exclusively uses 'ollama' (qwen3.5:4b)."
    )


def get_llm_provider() -> LLMChainProvider:
    """Get canonical LLM provider chain.

    In production, LLM_PROVIDER=ollama and LLM_MODEL=qwen3.5:4b route
    exclusively to Qwen35Provider with zero fallback.
    Mock providers are permitted only in isolated unit tests (Rule 5).
    """
    provider_name = _get_env("LLM_PROVIDER")
    chain_str = _get_env("LLM_PROVIDER_CHAIN")

    if provider_name and not chain_str:
        chain_str = provider_name
    if not chain_str:
        chain_str = "ollama"

    names = [n.strip() for n in chain_str.split(",") if n.strip()]
    providers = [_build_llm(n) for n in names]
    chain = LLMChainProvider(providers)

    is_ollama = bool(providers and getattr(providers[0], "name", "") == "ollama")
    chain.disable_fallback = _flag("LLM_DISABLE_FALLBACK", default="true" if is_ollama else "false")
    return chain


def _flag(name: str, default: str = "false") -> bool:
    """Get a boolean environment setting."""
    from django.conf import settings as dj_settings
    value = getattr(dj_settings, name, None)
    if value is None:
        value = os.environ.get(name, default)
    return str(value).strip() in ("1", "true", "True", "TRUE")


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
    """Get canonical embedding provider based on EMBEDDING_PROVIDER."""
    name = _get_env("EMBEDDING_PROVIDER")
    if not name:
        raise ValueError("EMBEDDING_PROVIDER is not configured")
    
    if name == "hashing":
        return HashingEmbeddingProvider()
    
    if name in ("sentence_transformers", "qwen3", "qwen", "qwen3-embedding", "Qwen/Qwen3-Embedding-0.6B"):
        from providers.embeddings.qwen3 import Qwen3EmbeddingProvider
        return Qwen3EmbeddingProvider()
    
    if name == "openai":
        raise ValueError("OpenAI embeddings provider not available (legacy hosted provider removed in favor of Qwen/Qwen3-Embedding-0.6B)")
    
    raise ValueError(f"Unknown embedding provider: {name}")


def embedding_model_version() -> str:
    """Get embedding model version for cache invalidation."""
    provider = _get_env("EMBEDDING_PROVIDER")
    if not provider:
        raise ValueError("EMBEDDING_PROVIDER is not configured")
    if provider in ("sentence_transformers", "qwen3", "qwen", "qwen3-embedding"):
        version = _get_env("EMBEDDING_MODEL_VERSION")
        if version and not version.startswith("hashing"):
            return version
        model_name = _get_env("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
        return f"{model_name.replace('/', '-')}-v1"
    return _get_env("EMBEDDING_MODEL_VERSION", "hashing-1024-v1")


def embedding_dimension() -> int:
    """Get embedding dimension for the current provider."""
    provider = _get_env("EMBEDDING_PROVIDER")
    if not provider:
        raise ValueError("EMBEDDING_PROVIDER is not configured")
    if provider in ("sentence_transformers", "qwen3", "qwen", "qwen3-embedding"):
        return int(_get_env("EMBEDDING_DIMENSIONS", "1024"))
    return int(_get_env("EMBEDDING_DIMENSIONS", "1024"))


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