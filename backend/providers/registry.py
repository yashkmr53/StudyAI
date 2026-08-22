"""Provider registry: business logic asks for a provider by role (§24).

Real handwriting providers are an open decision (§30); the default chain is
the mock provider, overridable via settings for tests.
"""
from django.conf import settings

from providers.base import EmbeddingProvider, LLMProvider, OCRProvider
from providers.ocr.chain import OCRChainProvider
from providers.storage.local import LocalObjectStorage


def get_object_storage() -> LocalObjectStorage:
    backend = settings.OBJECT_STORAGE_BACKEND
    if backend == "local":
        return LocalObjectStorage()
    raise ValueError(f"Unknown OBJECT_STORAGE_BACKEND: {backend}")


def _build_ocr(name: str):
    if name == "mock":
        from providers.ocr.mock import MockOCRProvider

        return MockOCRProvider()
    if name == "mock_low_confidence":
        from providers.ocr.mock import MockOCRProvider

        return MockOCRProvider(confidence=0.42, name="mock_low_confidence")
    if name == "failing":
        from providers.ocr.mock import MockOCRProvider

        return MockOCRProvider(fail=True, name="failing")
    raise ValueError(f"Unknown OCR provider: {name}")


def get_ocr_provider() -> OCRChainProvider:
    """Primary + fallback chain (§28). Defaults to mock → mock."""
    names = getattr(settings, "OCR_PROVIDER_CHAIN", ["mock", "mock"])
    return OCRChainProvider([_build_ocr(n) for n in names])


def _build_llm(name: str):
    if name == "mock":
        from providers.llm.mock import MockLLMProvider

        return MockLLMProvider()
    if name == "failing":
        from providers.llm.failing import FailingLLMProvider

        return FailingLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name}")


def get_llm_provider():
    """Primary → fallback chain (§28). Default: mock → mock."""
    from providers.llm.chain import LLMChainProvider

    names = getattr(settings, "LLM_PROVIDER_CHAIN", ["mock", "mock"])
    return LLMChainProvider([_build_llm(n) for n in names])


def get_embedding_provider() -> EmbeddingProvider:
    name = getattr(settings, "EMBEDDING_PROVIDER", "hashing")
    if name == "hashing":
        from providers.embeddings.hashing import HashingEmbeddingProvider

        return HashingEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {name}")


def embedding_model_version() -> str:
    return getattr(settings, "EMBEDDING_MODEL_VERSION", "hashing-384-v1")
