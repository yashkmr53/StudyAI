# Phase 11 Implementation Plan — Local-First Provider Architecture

**Date:** 2026-08-23  
**Source:** User requirements for local development without paid external services  
**Goal:** Implement complete local provider stack with provider abstraction layer enabling zero-code switching to production providers.

---

## Scope Summary

| Category | Implementation | Files |
|----------|----------------|-------|
| Provider Interfaces | Extended protocols for all 5 capabilities | `providers/base.py` |
| OCR | Tesseract + PaddleOCR providers | `providers/ocr/local.py`, `providers/ocr/__init__.py` |
| LLM | Ollama generate + chat providers | `providers/llm/local.py`, `providers/llm/__init__.py` |
| Embeddings | sentence-transformers + hashing fallback | `providers/embeddings/local.py`, `providers/embeddings/__init__.py` |
| Storage | MinIO/S3 via boto3 | `providers/storage/s3.py`, `providers/storage/__init__.py` |
| Email | Mailpit + SMTP + Console | `providers/email/__init__.py` |
| Registry | Env-var-driven selection with chains | `providers/registry.py` |
| Docker Compose | minio, mailpit, ollama services | `docker-compose.yml`, `backend/Dockerfile` |
| Tests | Contracts, behavior, selection, integration | `providers/tests/*.py` |
| Documentation | Local vs production guide | `docs/phase_11_local_providers.md` |

---

## Execution Order

### Sprint 1: Provider Interfaces & Registry (Day 1)
1. Extend `providers/base.py` protocols
2. Implement `providers/registry.py` with env-var selection
3. Chain fallback pattern for OCR/LLM

### Sprint 2: Local OCR Provider (Day 1-2)
1. `TesseractOCRProvider` using `tesserocr` bindings
2. `PaddleOCRProvider` as alternative
3. Integrate with `OCRChainProvider`
4. Add Tesseract to Dockerfile

### Sprint 3: Local LLM Provider (Day 2-3)
1. `OllamaLLMProvider` using `/api/generate`
2. `OllamaChatProvider` using `/api/chat`
3. Token counting, prompt injection, sanitization
4. Integrate with `LLMChainProvider`

### Sprint 4: Local Embeddings Provider (Day 3)
1. `SentenceTransformerEmbeddingProvider` with MiniLM
2. Dimension, normalization, version tracking
3. `embedding_model_version()`, `embedding_dimension()` helpers
4. Backfill strategy documentation

### Sprint 5: Local Storage Provider (Day 3-4)
1. `MinIOStorageProvider` / `S3StorageProvider` via boto3
2. Presigned URLs, byte operations, bucket management
3. Replace `OBJECT_STORAGE_BACKEND` with `STORAGE_BACKEND`

### Sprint 6: Local Email Provider (Day 4)
1. `MailpitEmailProvider` with SMTP + API
2. `SMTPEmailProvider` for production
3. `ConsoleEmailProvider` for tests
4. Password reset email template

### Sprint 7: Docker Compose Integration (Day 4-5)
1. Add minio, mailpit, ollama services
2. Update backend depends_on
3. Configure env vars in compose
4. Update Dockerfile with tesseract

### Sprint 8: Tests (Day 5-6)
1. Provider contract tests
2. Behavior tests per provider
3. Selection/integration tests
4. Backup/restore tests

### Sprint 9: Documentation (Day 6)
1. `.env.example` with all variables
2. `docs/phase_11_local_providers.md`
3. README, CHECKPOINT, IMPLEMENTATION_PLAN

---

## Detailed Implementation

### 1. Provider Interfaces (`providers/base.py`)

**Changes:**
- Add `dimension`, `model_name`, `model_version` properties to `EmbeddingProvider`
- Add `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd` to `StructuredLLMResult`
- Add `EmailProvider` protocol with `send_email` and `send_password_reset_email`
- Add `store_bytes`, `read_bytes`, `exists`, `size` to `ObjectStorageProvider`

**Verification:**
```bash
docker compose run --rm api python -c "
from providers.base import EmbeddingProvider, LLMProvider, OCRProvider, ObjectStorageProvider, EmailProvider
print('All protocols defined')
"
```

### 2. OCR Providers (`providers/ocr/local.py`)

**TesseractOCRProvider:**
- Uses `tesserocr.PyTessBaseAPI`
- Line-level results with bbox, confidence
- Language configurable via `languages` parameter
- Graceful degradation if tesserocr not installed

**PaddleOCRProvider:**
- Uses `paddleocr.PaddleOCR`
- Better for tables, handwriting, CJK
- Lazy model initialization
- Optional dependency

**Integration:**
- Export from `providers/ocr/__init__.py`
- Registry `_build_ocr()` handles "tesseract", "paddleocr"
- Chain fallback: `OCR_PROVIDER_CHAIN=tesseract,mock`

**Dockerfile:**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
```

**Requirements:**
```
tesserocr>=2.6.0
```

**Verification:**
```bash
docker compose run --rm api python -c "
from providers.ocr.local import TesseractOCRProvider
p = TesseractOCRProvider()
print(f'Tesseract available: {p._tesserocr is not None}')
"
docker compose exec api tesseract --version
```

### 3. LLM Providers (`providers/llm/local.py`)

**OllamaLLMProvider:**
- POST `/api/generate` with `format=json`
- JSON schema from Pydantic model
- Token counts from `prompt_eval_count`, `eval_count`
- Low temperature (0.1) for structured output

**OllamaChatProvider:**
- POST `/api/chat` with messages array
- Better structured output compliance
- Same token counting

**Security (in LLMChainProvider):**
- Prompt-injection directive prepended to system prompt
- PII sanitization (email, phone, credit card, SSN)
- Redaction count logged to `ProviderCallLog.metadata`

**Integration:**
- Export from `providers/llm/__init__.py`
- Registry `_build_llm()` handles "ollama", "ollama-chat"
- Chain fallback: `LLM_PROVIDER_CHAIN=ollama,mock`

**Verification:**
```bash
docker compose exec ollama ollama pull llama3.1:8b
docker compose run --rm api python -c "
from providers.llm.local import OllamaLLMProvider
p = OllamaLLMProvider()
print(f'Ollama model: {p.model}')
"
```

### 4. Embedding Providers (`providers/embeddings/local.py`)

**SentenceTransformerEmbeddingProvider:**
- `sentence-transformers/all-MiniLM-L6-v2` default
- Auto-detect device: CUDA > MPS > CPU
- L2 normalization via `normalize_embeddings=True`
- Batch encoding with configurable batch size
- Model version tracking for cache invalidation

**Properties:**
- `dimension` → 384
- `model_name` → "sentence-transformers/all-MiniLM-L6-v2"
- `model_version` → "sentence-transformers-all-MiniLM-L6-v2-v1"

**Registry Helpers:**
- `embedding_model_version()` → version string for cache keys
- `embedding_dimension()` → dimension for pgvector schema

**Backfill Strategy:**
```bash
# On model change:
# 1. Update EMBEDDING_MODEL_NAME
# 2. python manage.py backfill_embeddings --model-version=new-version
# 3. Update EMBEDDING_MODEL_VERSION in settings
```

**Requirements:**
```
sentence-transformers>=3.0
```

**Verification:**
```bash
docker compose run --rm api python -c "
from providers.embeddings.local import SentenceTransformerEmbeddingProvider
p = SentenceTransformerEmbeddingProvider()
emb = p.embed(['test'], model_version=p.model_version)
print(f'Dimension: {len(emb[0])}')
print(f'Normalized: {abs(sum(x*x for x in emb[0]) - 1.0) < 1e-5}')
"
```

### 5. Storage Providers (`providers/storage/s3.py`)

**MinIOStorageProvider / S3StorageProvider:**
- boto3 client with configurable endpoint
- Presigned URLs for upload/download (TTL configurable)
- Direct byte operations: `store_bytes`, `read_bytes`
- Bucket auto-creation on init
- Existence and size checks

**Registry Selection:**
- `STORAGE_BACKEND=local` → `LocalObjectStorage` (legacy)
- `STORAGE_BACKEND=minio` → `MinIOStorageProvider`
- `STORAGE_BACKEND=s3` → `S3StorageProvider` (validates credentials)

**Requirements:**
```
boto3>=1.34
```

**Verification:**
```bash
docker compose run --rm api python -c "
from providers.registry import get_object_storage
s = get_object_storage()
url = s.create_upload_url('test.txt', content_type='text/plain', ttl_seconds=300)
print(f'Upload URL: {url[:80]}...')
"
# Check MinIO console: http://localhost:9001
```

### 6. Email Providers (`providers/email/__init__.py`)

**MailpitEmailProvider:**
- SMTP to Mailpit (port 1025)
- Web UI at port 8025 for inspection
- `get_captured_emails()` for test assertions
- HTML + text multipart support

**SMTPEmailProvider:**
- TLS (port 587) or SSL (port 465)
- Optional authentication
- Same interface as Mailpit

**ConsoleEmailProvider:**
- Prints to stdout
- Captures in memory (`get_sent_emails()`)
- For test environments

**Registry Selection:**
- `EMAIL_BACKEND=mailpit` → `MailpitEmailProvider`
- `EMAIL_BACKEND=smtp` → `SMTPEmailProvider` (validates SMTP_HOST)
- `EMAIL_BACKEND=console` → `ConsoleEmailProvider`

**Verification:**
```bash
docker compose run --rm api python -c "
from providers.registry import get_email_provider
e = get_email_provider()
e.send_password_reset_email(to='test@example.com', reset_url='http://test/reset', user_name='Test')
print('Email sent')
"
# Check Mailpit UI: http://localhost:8025
```

### 7. Provider Registry (`providers/registry.py`)

**Key Functions:**
- `get_object_storage()` → STORAGE_BACKEND
- `get_ocr_provider()` → OCR_PROVIDER_CHAIN (comma-separated)
- `get_llm_provider()` → LLM_PROVIDER_CHAIN (comma-separated)
- `get_embedding_provider()` → EMBEDDING_PROVIDER
- `get_email_provider()` → EMAIL_BACKEND
- `embedding_model_version()` / `embedding_dimension()`

**Production Fail-Fast:**
```python
if name == "openai" and not _get_env("OPENAI_API_KEY"):
    raise ValueError("OpenAI provider requires OPENAI_API_KEY")
```

**Verification:**
```bash
docker compose run --rm api python -c "
from providers.registry import *
print('Storage:', type(get_object_storage()).__name__)
print('OCR:', type(get_ocr_provider()).__name__)
print('LLM:', type(get_llm_provider()).__name__)
print('Embedding:', type(get_embedding_provider()).__name__)
print('Email:', type(get_email_provider()).__name__)
print('Embedding version:', embedding_model_version())
print('Embedding dim:', embedding_dimension())
"
```

### 8. Docker Compose (`docker-compose.yml`)

**New Services:**
```yaml
minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
    MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-minioadmin}
  ports: ["9000:9000", "9001:9001"]
  volumes: [minio_data:/data]

mailpit:
  image: axllent/mailpit:latest
  ports: ["1025:1025", "8025:8025"]
  environment:
    MP_SMTP_AUTH_ACCEPT_ANY: 1

ollama:
  image: ollama/ollama:latest
  ports: ["11434:11434"]
  volumes: [ollama_data:/root/.ollama]
```

**Backend Environment:**
```yaml
environment:
  STORAGE_BACKEND: ${STORAGE_BACKEND:-minio}
  MINIO_ENDPOINT: http://minio:9000
  MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:-minioadmin}
  MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:-minioadmin}
  MINIO_BUCKET: ${MINIO_BUCKET:-studyai}
  OCR_PROVIDER_CHAIN: ${OCR_PROVIDER_CHAIN:-tesseract,mock}
  LLM_PROVIDER_CHAIN: ${LLM_PROVIDER_CHAIN:-ollama,mock}
  EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:-sentence_transformers}
  EMBEDDING_MODEL_NAME: ${EMBEDDING_MODEL_NAME:-sentence-transformers/all-MiniLM-L6-v2}
  EMAIL_BACKEND: ${EMAIL_BACKEND:-mailpit}
  MAILPIT_HOST: mailpit
  MAILPIT_PORT: 1025
  MAILPIT_API_URL: http://mailpit:8025
  OLLAMA_BASE_URL: http://ollama:11434
  LLM_MODEL: ${LLM_MODEL:-llama3.1:8b}
```

**Verification:**
```bash
docker compose up -d
docker compose ps  # All services healthy
docker compose logs ollama | grep "listening on"
```

### 9. Tests (`providers/tests/`)

**Test Files:**
| File | Coverage |
|------|----------|
| `test_providers.py` | Contracts, selection, local startup, invalid config, switching |
| `test_ocr.py` | Mock/Tesseract/PaddleOCR behavior, chain fallback |
| `test_llm.py` | Mock/Ollama behavior, prompt injection, sanitization, chain fallback |
| `test_embeddings.py` | Hashing/sentence-transformers, normalization, backfill |
| `test_storage.py` | Local/MinIO operations, interface compliance |
| `test_email.py` | Console/Mailpit/SMTP delivery, interface compliance |
| `test_backup.py` | Backup commands, MinIO backup/restore, offsite hook |

**Run All:**
```bash
docker compose run --rm api python -m pytest backend/providers/tests/ -v
```

**Expected:** All tests pass (contract compliance, local provider behavior, registry selection, chain fallback, production credential validation)

---

## Verification Checklist (Phase 11 Done)

| Item | Verification Command |
|------|---------------------|
| All Docker services healthy | `docker compose ps` |
| Ollama model pulled | `docker compose exec ollama ollama list` |
| Tesseract OCR works | `docker compose run --rm api python -c "from providers.ocr.local import TesseractOCRProvider; p=TesseractOCRProvider(); print(p.recognize('test.jpg', request_id='1'))"` |
| Ollama LLM generates | `docker compose run --rm api python -c "from providers.llm.local import OllamaLLMProvider; p=OllamaLLMProvider(); r=p.generate_structured(prompt=Prompt(name='chat',version='v1',user='hi'), schema=dict, request_id='1'); print(r.data)"` |
| Embeddings generated | `docker compose run --rm api python -c "from providers.embeddings.local import SentenceTransformerEmbeddingProvider; p=SentenceTransformerEmbeddingProvider(); e=p.embed(['test'], model_version=p.model_version); print(len(e[0]))"` |
| MinIO upload/download | `docker compose run --rm api python -c "from providers.registry import get_object_storage; s=get_object_storage(); s.store_bytes('test',b'data'); print(s.read_bytes('test'))"` |
| Mailpit captures email | `curl http://localhost:8025/api/v1/messages` |
| All provider tests pass | `docker compose run --rm api python -m pytest backend/providers/tests/ -v` |
| Provider switching works | Change env vars, restart, verify registry returns different types |

---

## Files Created/Modified Summary

### Backend (New)
```
backend/providers/base.py                    (extended)
backend/providers/ocr/local.py               (new)
backend/providers/ocr/__init__.py            (updated)
backend/providers/llm/local.py               (new)
backend/providers/llm/__init__.py            (updated)
backend/providers/embeddings/local.py        (new)
backend/providers/embeddings/__init__.py     (updated)
backend/providers/storage/s3.py              (new)
backend/providers/storage/__init__.py        (updated)
backend/providers/email/__init__.py          (new)
backend/providers/registry.py                (rewritten)
backend/providers/tests/test_providers.py    (new)
backend/providers/tests/test_ocr.py          (new)
backend/providers/tests/test_llm.py          (new)
backend/providers/tests/test_embeddings.py   (new)
backend/providers/tests/test_storage.py      (new)
backend/providers/tests/test_email.py        (new)
backend/providers/tests/test_backup.py       (new)
backend/providers/tests/__init__.py          (new)
```

### Backend (Modified)
```
backend/requirements.txt                     (added deps)
backend/Dockerfile                           (added tesseract)
backend/config/settings/base.py              (env vars documented)
```

### Docker/Config
```
docker-compose.yml                           (added minio, mailpit, ollama)
.env.example                                 (all provider vars)
```

### Documentation
```
docs/phase_11/README.md
docs/phase_11/CHECKPOINT.md
docs/phase_11/PHASE_11_IMPLEMENTATION_PLAN.md
docs/phase_11_local_providers.md
```

---

## Environment Variables to Document (`.env.example`)

```bash
# --- Object Storage (STORAGE_BACKEND: local | minio | s3) ---
STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai
MINIO_REGION=us-east-1
MINIO_SECURE=false

# Production S3
# STORAGE_BACKEND=s3
# S3_BUCKET=studyai-prod
# S3_REGION=us-east-1
# S3_ACCESS_KEY=<aws-access-key>
# S3_SECRET_KEY=<aws-secret-key>
# S3_SECURE=true

# --- OCR (OCR_PROVIDER_CHAIN: comma-separated primary,fallback) ---
OCR_PROVIDER_CHAIN=tesseract,mock
# Options: mock, tesseract, paddleocr, google

# Production
# OCR_PROVIDER_CHAIN=google,mock
# OCR_API_KEY=<google-cloud-vision-key>

# --- LLM (LLM_PROVIDER_CHAIN: comma-separated primary,fallback) ---
LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b
# Options: mock, ollama, ollama-chat, openai, anthropic

# Production
# LLM_PROVIDER_CHAIN=openai,mock
# OPENAI_API_KEY=<openai-key>
# LLM_MODEL=gpt-4o-mini

# --- Embeddings (EMBEDDING_PROVIDER: hashing | sentence_transformers | openai) ---
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto

# Production
# EMBEDDING_PROVIDER=openai
# OPENAI_API_KEY=<openai-key>

# --- Email (EMAIL_BACKEND: mailpit | smtp | console) ---
EMAIL_BACKEND=mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
EMAIL_FROM=noreply@studyai.local

# Production
# EMAIL_BACKEND=smtp
# SMTP_HOST=smtp.sendgrid.net
# SMTP_PORT=587
# SMTP_USERNAME=apikey
# SMTP_PASSWORD=<sendgrid-api-key>
# SMTP_USE_TLS=true
```

---

## Dependencies Between Tasks

```
Provider Interfaces (base.py)
    │
    ├─► Registry (registry.py) ◄──────────────────────┐
    │                                                  │
    ├─► OCR (local.py) ────────────────────────────────┤
    │                                                  │
    ├─► LLM (local.py) ────────────────────────────────┤ (all use registry)
    │                                                  │
    ├─► Embeddings (local.py) ────────────────────────┤
    │                                                  │
    ├─► Storage (s3.py) ──────────────────────────────┤
    │                                                  │
    └─► Email (__init__.py) ──────────────────────────┘
            │
            ▼
    Docker Compose (all services)
            │
            ▼
    Tests (verify all providers)
            │
            ▼
    Documentation
```

---

## Rollback Plan

| Component | Rollback Action |
|-----------|-----------------|
| Provider interfaces | Revert `providers/base.py` to previous version |
| OCR providers | Remove `providers/ocr/local.py`, revert `__init__.py`, remove tesseract from Dockerfile |
| LLM providers | Remove `providers/llm/local.py`, revert `__init__.py` |
| Embedding providers | Remove `providers/embeddings/local.py`, revert `__init__.py` |
| Storage providers | Remove `providers/storage/s3.py`, revert `__init__.py` |
| Email providers | Remove `providers/email/__init__.py` |
| Registry | Revert `providers/registry.py` to Phase 10 version |
| Docker Compose | Remove minio, mailpit, ollama services; remove env vars |
| Tests | Remove `providers/tests/` directory |
| Dependencies | Remove tesserocr, sentence-transformers, boto3 from requirements.txt |

---

## Next Phase (Phase 12) Preview

With local-first architecture complete, Phase 12 focuses on production readiness:

1. **Production Provider Adapters**
   - `providers/ocr/google.py` — Google Cloud Vision
   - `providers/llm/openai.py` — OpenAI GPT-4o/GPT-4o-mini
   - `providers/llm/anthropic.py` — Anthropic Claude
   - `providers/embeddings/openai.py` — OpenAI text-embedding-3-small
   - `providers/storage/s3.py` — Already supports S3 via `S3StorageProvider`
   - `providers/email/smtp.py` — Already implemented as `SMTPEmailProvider`

2. **Golden Dataset & Evaluation (F1)**
   - Author 30–50 labeled notes
   - Calibrate EvidenceVerifier thresholds
   - Tune Mastery EMA constants and planner weights

3. **Frontend Modules (G1–G4)**
   - AI Classroom UI
   - Tests UI
   - Chat UI
   - Revision Planner UI

4. **Production Deployment**
   - TLS/HTTPS (Let's Encrypt or managed)
   - Non-superuser DB role (A3)
   - Monitoring (Sentry, Prometheus, Grafana)
   - Load testing at production scale

All provider interfaces are stable — production adapters plug into existing registry without business logic changes.