# Phase 11 Changelog

## 2026-08-23 — Initial Release (v11.0.0)

### Added
- **Provider Interfaces** (`providers/base.py`)
  - Extended `EmbeddingProvider` with `dimension`, `model_name`, `model_version` properties
  - Extended `StructuredLLMResult` with token counting fields (`input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`)
  - Added `EmailProvider` protocol with `send_email` and `send_password_reset_email`
  - Added `store_bytes`, `read_bytes`, `exists`, `size` to `ObjectStorageProvider`

- **OCR Providers** (`providers/ocr/local.py`)
  - `TesseractOCRProvider` — Uses `tesserocr` bindings, line-level results with bbox/confidence
  - `PaddleOCRProvider` — Alternative for complex layouts/CJK, lazy model loading
  - Both integrate with `OCRChainProvider` for fallback

- **LLM Providers** (`providers/llm/local.py`)
  - `OllamaLLMProvider` — Uses Ollama `/api/generate` with JSON schema constrained output
  - `OllamaChatProvider` — Uses Ollama `/api/chat` for better structured output
  - Token counting via `prompt_eval_count` / `eval_count`
  - Prompt-injection directive and PII sanitization in `LLMChainProvider`

- **Embedding Providers** (`providers/embeddings/local.py`)
  - `SentenceTransformerEmbeddingProvider` — Runs `sentence-transformers/all-MiniLM-L6-v2` locally
    - 384 dimensions, L2 normalized, cosine similarity via dot product
    - Auto-detect device (CUDA/MPS/CPU), configurable batch size
    - Model version tracking for cache invalidation
  - `HashingEmbeddingProvider` — Retained as deterministic fallback
  - Registry helpers: `embedding_model_version()`, `embedding_dimension()`

- **Storage Providers** (`providers/storage/s3.py`)
  - `MinIOStorageProvider` — S3-compatible via boto3, presigned URLs, bucket auto-creation
  - `S3StorageProvider` — Production S3 alias with credential validation
  - Replaces `OBJECT_STORAGE_BACKEND` with `STORAGE_BACKEND`

- **Email Providers** (`providers/email/__init__.py`)
  - `MailpitEmailProvider` — Local SMTP + Web UI (port 8025) + API for test inspection
  - `SMTPEmailProvider` — Production SMTP with TLS/SSL, optional auth
  - `ConsoleEmailProvider` — Prints to stdout, captures in memory for tests

- **Provider Registry** (`providers/registry.py`)
  - Centralized env-var-driven selection for all 5 capabilities
  - Chain fallback syntax: `primary,fallback` (e.g., `ollama,mock`)
  - Production providers fail fast on missing credentials
  - No silent fallback from production → local

- **Docker Compose** (`docker-compose.yml`)
  - Added `minio` (ports 9000/9001) — S3 API + Console
  - Added `mailpit` (ports 1025/8025) — SMTP + Web UI
  - Added `ollama` (port 11434) — LLM API + Model storage
  - Backend depends on all three for local development

- **Tests** (`providers/tests/`)
  - `test_providers.py` — Contracts, selection, local startup, invalid config, switching
  - `test_ocr.py` — Mock/Tesseract/PaddleOCR behavior, chain fallback
  - `test_llm.py` — Mock/Ollama behavior, prompt injection, sanitization, chain fallback
  - `test_embeddings.py` — Hashing/sentence-transformers, normalization, backfill
  - `test_storage.py` — Local/MinIO operations, interface compliance
  - `test_email.py` — Console/Mailpit/SMTP delivery, interface compliance
  - `test_backup.py` — Backup commands, MinIO backup/restore, offsite hook

- **Documentation**
  - `docs/phase_11_local_providers.md` — Comprehensive local vs production guide
  - `docs/phase_11/README.md` — Phase overview
  - `docs/phase_11/CHECKPOINT.md` — Sprint tracking
  - `docs/phase_11/PHASE_11_IMPLEMENTATION_PLAN.md` — Full implementation spec

- **Configuration**
  - Updated `.env.example` with all provider variables (local + production)
  - Updated `backend/Dockerfile` with tesseract-ocr system dependency
  - Updated `backend/requirements.txt` with tesserocr, sentence-transformers, boto3

### Changed
- `providers/registry.py` — Complete rewrite with chain fallback and production fail-fast
- `providers/ocr/__init__.py` — Export new local providers
- `providers/llm/__init__.py` — Export new local providers
- `providers/embeddings/__init__.py` — Export new local providers
- `providers/storage/__init__.py` — Export MinIO/S3 providers
- `docker-compose.yml` — Added minio, mailpit, ollama services with healthchecks
- `backend/Dockerfile` — Added tesseract-ocr, tesseract-ocr-eng packages
- `backend/requirements.txt` — Added tesserocr, sentence-transformers, boto3, ollama

### Security
- Production providers validate required credentials at registry initialization
- Missing credentials → `ValueError` at startup (fail fast)
- No silent fallback from production → local providers
- Prompt-injection directive and PII sanitization applied in LLM chain
- All credentials via environment variables only (never in source control)

### Testing
- All provider tests pass in Docker environment
- Contract tests verify protocol compliance
- Behavior tests verify local provider functionality
- Integration tests verify registry selection and chain fallback
- Backup/restore tests verify MinIO storage operations

### Migration Notes
From Phase 10 configuration:
```bash
# Old (Phase 10)
OBJECT_STORAGE_BACKEND=local
OCR_PROVIDER_CHAIN=mock,mock
LLM_PROVIDER_CHAIN=mock,mock
EMBEDDING_PROVIDER=hashing

# New (Phase 11)
STORAGE_BACKEND=minio
OCR_PROVIDER_CHAIN=tesseract,mock
LLM_PROVIDER_CHAIN=ollama,mock
EMBEDDING_PROVIDER=sentence_transformers
```

Run after updating `.env`:
```bash
docker compose up -d
docker compose exec ollama ollama pull llama3.1:8b
docker compose run --rm api python manage.py migrate
```