# Phase 11 Architecture — Local-First Provider System

**Date:** 2026-08-23  
**Status:** IMPLEMENTED

---

## Overview

Phase 11 introduces a **provider abstraction layer** that decouples business logic from external service implementations. All capabilities (OCR, LLM, Embeddings, Storage, Email) are accessed through protocols defined in `providers/base.py`. Provider selection is driven entirely by environment variables, enabling zero-code switching between local and production providers.

---

## Provider Protocol Layer

```
┌─────────────────────────────────────────────────────────────────┐
│                        Business Logic                           │
│  (apps/enrichment, apps/chat, apps/questions, apps/documents)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Provider Protocols                         │
│  (providers/base.py)                                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ OCRProvider │ │ LLMProvider │ │EmbeddingProv│ │StorageProv│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    EmailProvider                         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Provider Registry                          │
│  (providers/registry.py)                                        │
│  Env-var selection → Concrete Implementation                    │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────────┐ ┌─────────────┐ ┌─────────────┐
│    Local (Dev)      │ │  Production │ │   Test      │
│  ─────────────────  │ │  ─────────  │ │  ─────────  │
│ OCR: Tesseract      │ │ OCR: Google │ │ OCR: Mock   │
│ LLM: Ollama         │ │ LLM: OpenAI │ │ LLM: Mock   │
│ Embed: MiniLM       │ │ Embed:OpenAI│ │ Embed:Hash  │
│ Storage: MinIO      │ │ Storage: S3 │ │ Storage:Loc │
│ Email: Mailpit      │ │ Email: SMTP │ │ Email:Console│
└─────────────────────┘ └─────────────┘ └─────────────┘
```

---

## Protocol Definitions (`providers/base.py`)

### OCRProvider
```python
@runtime_checkable
class OCRProvider(Protocol):
    def recognize(self, image_uri: str, *, request_id: str) -> OCRResult: ...

@dataclass
class OCRResult:
    lines: list[dict] = field(default_factory=list)  # {text, bbox, confidence}
    confidence: float = 0.0                          # Average confidence
    provider: str = ""                               # Provider name
    raw_ref: str | None = None                       # Source image reference
```

### LLMProvider
```python
@runtime_checkable
class LLMProvider(Protocol):
    def generate_structured(
        self, *, prompt: Prompt, schema: type, request_id: str
    ) -> StructuredLLMResult: ...

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
    input_tokens: int = 0          # For budget tracking
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
```

### EmbeddingProvider
```python
@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str], *, model_version: str) -> list[list[float]]: ...
    
    @property
    def dimension(self) -> int: ...              # Vector dimension (e.g., 384)
    
    @property
    def model_name(self) -> str: ...             # HF model identifier
    
    @property
    def model_version(self) -> str: ...          # Version for cache keys
```

### ObjectStorageProvider
```python
@runtime_checkable
class ObjectStorageProvider(Protocol):
    def create_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str: ...
    def create_download_url(self, key: str, *, ttl_seconds: int) -> str: ...
    def delete(self, key: str) -> None: ...
    def store_bytes(self, key: str, data: bytes) -> int: ...
    def read_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
```

### EmailProvider
```python
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
```

---

## Provider Chain Pattern

Both OCR and LLM use chain providers for fallback:

### OCRChainProvider (`providers/ocr/chain.py`)
```python
class OCRChainProvider:
    def __init__(self, providers: list[OCRProvider]):
        self.providers = providers
    
    def recognize(self, image_uri: str, *, request_id: str) -> tuple[OCRResult, list[str]]:
        # Try each provider in order
        # Log each attempt to ProviderCallLog
        # Return first success
        # Raise ProviderError if all fail
```

### LLMChainProvider (`providers/llm/chain.py`)
```python
class LLMChainProvider:
    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers
    
    def generate_structured(self, *, prompt: Prompt, schema=None, request_id: str) -> StructuredLLMResult:
        # Try each provider in order
        # Prepend prompt-injection directive (D4)
        # Sanitize user input for PII (D5)
        # Log token counts and redaction count
        # Return first success
        # Raise ProviderError if all fail
```

**Chain Configuration:**
```env
OCR_PROVIDER_CHAIN=tesseract,mock      # Primary: Tesseract, Fallback: Mock
LLM_PROVIDER_CHAIN=ollama,mock         # Primary: Ollama, Fallback: Mock
```

---

## Registry Selection Logic (`providers/registry.py`)

### Environment Variable Mapping

| Capability | Env Var | Local Default | Production Example |
|------------|---------|---------------|-------------------|
| OCR | `OCR_PROVIDER_CHAIN` | `tesseract,mock` | `google,mock` |
| LLM | `LLM_PROVIDER_CHAIN` | `ollama,mock` | `openai,mock` |
| Embeddings | `EMBEDDING_PROVIDER` | `sentence_transformers` | `openai` |
| Storage | `STORAGE_BACKEND` | `minio` | `s3` |
| Email | `EMAIL_BACKEND` | `mailpit` | `smtp` |

### Selection Functions

```python
def get_ocr_provider() -> OCRChainProvider:
    names = _get_env("OCR_PROVIDER_CHAIN", "mock,mock").split(",")
    return OCRChainProvider([_build_ocr(n) for n in names])

def get_llm_provider() -> LLMChainProvider:
    names = _get_env("LLM_PROVIDER_CHAIN", "mock,mock").split(",")
    return LLMChainProvider([_build_llm(n) for n in names])

def get_embedding_provider() -> EmbeddingProvider:
    name = _get_env("EMBEDDING_PROVIDER", "hashing")
    if name == "hashing": return HashingEmbeddingProvider()
    if name == "sentence_transformers": return SentenceTransformerEmbeddingProvider()
    if name == "openai": return OpenAIEmbeddingProvider()  # Requires OPENAI_API_KEY

def get_object_storage() -> ObjectStorageProvider:
    backend = _get_env("STORAGE_BACKEND", "local")
    if backend == "local": return LocalObjectStorage()
    if backend == "minio": return MinIOStorageProvider()
    if backend == "s3": return S3StorageProvider()  # Validates credentials

def get_email_provider() -> EmailProvider:
    backend = _get_env("EMAIL_BACKEND", "mailpit")
    if backend == "mailpit": return MailpitEmailProvider()
    if backend == "smtp": return SMTPEmailProvider()  # Validates SMTP_HOST
    if backend == "console": return ConsoleEmailProvider()
```

### Production Fail-Fast

```python
def _build_llm(name: str):
    if name == "openai":
        if not _get_env("OPENAI_API_KEY"):
            raise ValueError("OpenAI provider requires OPENAI_API_KEY")
        return OpenAILLMProvider()
    # ...
```

---

## Local Provider Implementations

### OCR: Tesseract (`providers/ocr/local.py`)

**TesseractOCRProvider**
- Uses `tesserocr` Python bindings (C API wrapper)
- Runs inside backend container
- Line-level results via `RIL.TEXTLINE` iterator
- Configurable languages (default: English)

**PaddleOCRProvider**
- Uses `paddleocr` Python package
- Better for: tables, handwriting, CJK, complex layouts
- Lazy model initialization (downloads ~1GB on first use)
- Optional dependency

### LLM: Ollama (`providers/llm/local.py`)

**OllamaLLMProvider** (Generate API)
- POST `http://ollama:11434/api/generate`
- `format=json` for schema-constrained output
- Low temperature (0.1) for determinism
- Token counts from `prompt_eval_count`, `eval_count`

**OllamaChatProvider** (Chat API)
- POST `http://ollama:11434/api/chat`
- Messages array format
- Better structured output compliance

### Embeddings: sentence-transformers (`providers/embeddings/local.py`)

**SentenceTransformerEmbeddingProvider**
- Model: `sentence-transformers/all-MiniLM-L6-v2` (default)
- Dimensions: 384
- Normalization: L2 (unit vectors)
- Similarity: Cosine = dot product on normalized vectors
- Device auto-detection: CUDA > MPS > CPU
- Batch encoding with configurable batch size

**Model Metadata:**
| Property | Value |
|----------|-------|
| `dimension` | 384 |
| `model_name` | `sentence-transformers/all-MiniLM-L6-v2` |
| `model_version` | `sentence-transformers-all-MiniLM-L6-v2-v1` |
| Normalization | L2 |
| Similarity | Cosine (dot product) |
| Persistence | Float32 array (pgvector) |

### Storage: MinIO/S3 (`providers/storage/s3.py`)

**MinIOStorageProvider / S3StorageProvider**
- Single implementation via `boto3`
- Endpoint, credentials, bucket, region configurable
- Presigned URLs for upload/download (TTL configurable)
- Direct byte operations for internal use
- Bucket auto-creation on initialization

### Email: Mailpit/SMTP (`providers/email/__init__.py`)

**MailpitEmailProvider**
- SMTP to `mailpit:1025`
- Web UI at `http://mailpit:8025`
- API for test inspection: `GET /api/v1/messages`
- Multipart HTML + text support

**SMTPEmailProvider**
- TLS (587) or SSL (465)
- Optional authentication
- Same interface as Mailpit

**ConsoleEmailProvider**
- Prints to stdout
- Captures in memory for test assertions
- `get_sent_emails()`, `clear_sent_emails()`

---

## Data Flow Examples

### Document Ingestion with OCR
```
1. User uploads image → API
2. API calls get_ocr_provider().recognize(image_uri, request_id)
3. Registry returns OCRChainProvider([TesseractOCRProvider, MockOCRProvider])
4. Chain tries Tesseract first
5. On success: OCRResult with lines, confidence, provider="tesseract"
6. On failure: Falls back to Mock, logs attempt to ProviderCallLog
7. Result passed to ingestion pipeline
```

### LLM Enrichment/Chat
```
1. Pipeline builds Prompt with evidence JSON
2. Calls get_llm_provider().generate_structured(prompt, schema, request_id)
3. Registry returns LLMChainProvider([OllamaLLMProvider, MockLLMProvider])
4. Chain prepends prompt-injection directive (D4)
5. Chain sanitizes user input for PII (D5)
6. Calls Ollama /api/generate with JSON schema
7. Logs token counts, redaction count to ProviderCallLog
8. Returns StructuredLLMResult with data, model, token counts
```

### Embedding Generation
```
1. Chunker produces text chunks
2. Calls get_embedding_provider().embed(texts, model_version=embedding_model_version())
3. Registry returns SentenceTransformerEmbeddingProvider
4. Batch encodes with normalize_embeddings=True
5. Returns list[list[float]] (384-dim, L2 normalized)
6. Stored in pgvector column on NoteChunk
```

### File Upload/Download
```
1. Frontend requests upload URL → API
2. API calls get_object_storage().create_upload_url(key, content_type, ttl)
3. Registry returns MinIOStorageProvider
4. MinIO generates presigned PUT URL
5. Frontend PUTs directly to MinIO
6. On download: create_download_url → presigned GET URL
```

### Password Reset Email
```
1. User requests password reset → API
2. API calls get_email_provider().send_password_reset_email(to, reset_url, user_name)
3. Registry returns MailpitEmailProvider (dev) or SMTPEmailProvider (prod)
4. Provider sends via SMTP
5. Dev: Captured in Mailpit UI (http://localhost:8025)
6. Prod: Delivered via SendGrid/SMTP
```

---

## Configuration Matrix

### Development (`.env`)
```env
STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai

OCR_PROVIDER_CHAIN=tesseract,mock

LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b

EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto

EMAIL_BACKEND=mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
```

### Production (`.env.production`)
```env
STORAGE_BACKEND=s3
S3_BUCKET=studyai-prod
S3_REGION=us-east-1
S3_ACCESS_KEY=<aws-key>
S3_SECRET_KEY=<aws-secret>

OCR_PROVIDER_CHAIN=google,mock
OCR_API_KEY=<google-vision-key>

LLM_PROVIDER_CHAIN=openai,mock
OPENAI_API_KEY=<openai-key>
LLM_MODEL=gpt-4o-mini

EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<openai-key>

EMAIL_BACKEND=smtp
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<sendgrid-key>
SMTP_USE_TLS=true
```

---

## Security Considerations

1. **Credential Isolation**: All secrets via environment variables only
2. **Fail-Fast**: Production providers raise `ValueError` at startup if credentials missing
3. **No Silent Fallback**: Chain fallback is explicit in env vars, not automatic
4. **Prompt Injection Defense**: Directive prepended to all LLM system prompts
5. **Data Minimization**: PII redacted before sending to LLM providers
6. **Audit Logging**: All provider calls logged to `ProviderCallLog` with metadata

---

## Testing Strategy

| Test Type | Coverage |
|-----------|----------|
| Contract | All providers implement protocols |
| Unit | Individual provider behavior (mocked deps) |
| Integration | Registry selection, chain fallback |
| E2E | Docker Compose full stack |

Run: `docker compose run --rm api python -m pytest backend/providers/tests/ -v`

---

## Extensibility

Adding a new provider:
1. Implement protocol in appropriate package (`ocr/`, `llm/`, `embeddings/`, `storage/`, `email/`)
2. Export from package `__init__.py`
3. Add builder in `providers/registry.py` with env var
4. Add tests in `providers/tests/`
5. Update `.env.example` and documentation

No business logic changes required.