"""Provider abstraction (architecture §24, §64).

Business logic depends on these protocols only; provider SDKs must not
leak into apps.
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class OCRResult:
    lines: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    provider: str = ""
    raw_ref: str | None = None


@dataclass
class Prompt:
    name: str
    version: str
    system: str = ""
    user: str = ""


@dataclass
class StructuredLLMResult:
    data: dict
    model: str = ""
    prompt_name: str = ""
    prompt_version: str = ""


@runtime_checkable
class OCRProvider(Protocol):
    def recognize(self, image_uri: str, *, request_id: str) -> OCRResult: ...


@runtime_checkable
class LLMProvider(Protocol):
    def generate_structured(self, *, prompt: Prompt, schema: type, request_id: str) -> StructuredLLMResult: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str], *, model_version: str) -> list[list[float]]: ...


@runtime_checkable
class ObjectStorageProvider(Protocol):
    def create_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str: ...
    def create_download_url(self, key: str, *, ttl_seconds: int) -> str: ...
    def delete(self, key: str) -> None: ...
