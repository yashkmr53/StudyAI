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
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@runtime_checkable
class OCRProvider(Protocol):
    def recognize(self, image_uri: str, *, request_id: str) -> OCRResult: ...


@runtime_checkable
class LLMProvider(Protocol):
    def generate_structured(self, *, prompt: Prompt, schema: type, request_id: str) -> StructuredLLMResult: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str], *, model_version: str) -> list[list[float]]: ...
    
    @property
    def dimension(self) -> int: ...
    
    @property
    def model_name(self) -> str: ...
    
    @property
    def model_version(self) -> str: ...


@runtime_checkable
class ObjectStorageProvider(Protocol):
    def create_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str: ...
    def create_download_url(self, key: str, *, ttl_seconds: int) -> str: ...
    def delete(self, key: str) -> None: ...
    def store_bytes(self, key: str, data: bytes) -> int: ...
    def read_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...


@runtime_checkable
class EmailProvider(Protocol):
    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_email: str | None = None,
    ) -> None: ...
    
    def send_password_reset_email(
        self,
        *,
        to: str,
        reset_url: str,
        user_name: str,
    ) -> None: ...
