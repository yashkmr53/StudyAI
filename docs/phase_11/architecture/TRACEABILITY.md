# Phase 11 — Traceability Matrix

**Date:** 2026-08-23

---

## Requirements → Implementation Mapping

| Requirement | Source | Implementation | Tests | Docs |
|-------------|--------|----------------|-------|------|
| Provider abstraction layer | User req | `providers/base.py` protocols | `test_providers.py::TestProviderContracts` | `ARCHITECTURE.md` |
| Local OCR without cloud creds | User req | `TesseractOCRProvider`, `PaddleOCRProvider` | `test_ocr.py` | `local_providers.md` |
| Local LLM without cloud creds | User req | `OllamaLLMProvider`, `OllamaChatProvider` | `test_llm.py` | `local_providers.md` |
| Local embeddings | User req | `SentenceTransformerEmbeddingProvider` | `test_embeddings.py` | `local_providers.md` |
| MinIO/S3 storage | User req | `MinIOStorageProvider`, `S3StorageProvider` | `test_storage.py` | `local_providers.md` |
| Local email testing | User req | `MailpitEmailProvider`, `ConsoleEmailProvider` | `test_email.py` | `local_providers.md` |
| Env-var provider selection | User req | `providers/registry.py` | `test_providers.py::TestProviderSelection` | `ARCHITECTURE.md` |
| Chain fallback (primary→fallback) | Architecture §28 | `OCRChainProvider`, `LLMChainProvider` | `test_ocr.py`, `test_llm.py` | `SYSTEM_FLOWS.md` |
| Production fail-fast | Security req | Registry validation | `test_providers.py::TestInvalidProviderConfiguration` | `ARCHITECTURE.md` |
| Docker Compose local stack | User req | minio, mailpit, ollama services | Integration tests | `local_providers.md` |
| Prompt-injection defense | Phase 10 D4 | `LLMChainProvider` prepends directive | `test_llm.py` | `ARCHITECTURE.md` |
| Data-minimization (PII redaction) | Phase 10 D5 | `LLMChainProvider` sanitizes input | `test_llm.py` | `ARCHITECTURE.md` |
| Token counting for budgets | Phase 10 B8 | `StructuredLLMResult` token fields | `test_llm.py` | `ARCHITECTURE.md` |
| Embedding versioning/backfill | Phase 10 B9 | `embedding_model_version()`, `embedding_dimension()` | `test_embeddings.py` | `local_providers.md` |

---

## Gap Analysis Coverage

| Gap ID | Description | Phase 11 Resolution |
|--------|-------------|---------------------|
| A1 | Real OCR provider | **Local alternative**: Tesseract/PaddleOCR implemented; Google Vision adapter stubbed |
| A2 | Real LLM provider | **Local alternative**: Ollama implemented; OpenAI/Anthropic adapters stubbed |
| B9 | Neural embedding model | **Implemented**: sentence-transformers/all-MiniLM-L6-v2 local |
| B10 | S3-compatible storage | **Implemented**: MinIO (local) + S3StorageProvider (production) |
| B3 | Password reset email | **Local alternative**: Mailpit; SMTP adapter for production |
| C4 | TLS termination | Out of scope — Phase 12 |
| F1 | Golden dataset | Out of scope — Phase 12 |

---

## File Traceability

| Feature | Protocol | Implementation | Registry | Tests | Config |
|---------|----------|----------------|----------|-------|--------|
| **OCR** | `OCRProvider` in `base.py` | `ocr/local.py` | `_build_ocr()` | `test_ocr.py` | `OCR_PROVIDER_CHAIN` |
| **LLM** | `LLMProvider` in `base.py` | `llm/local.py` | `_build_llm()` | `test_llm.py` | `LLM_PROVIDER_CHAIN` |
| **Embeddings** | `EmbeddingProvider` in `base.py` | `embeddings/local.py` | `get_embedding_provider()` | `test_embeddings.py` | `EMBEDDING_PROVIDER` |
| **Storage** | `ObjectStorageProvider` in `base.py` | `storage/s3.py` | `get_object_storage()` | `test_storage.py` | `STORAGE_BACKEND` |
| **Email** | `EmailProvider` in `base.py` | `email/__init__.py` | `get_email_provider()` | `test_email.py` | `EMAIL_BACKEND` |

---

## Environment Variable Traceability

| Env Var | Used In | Default (Dev) | Production |
|---------|---------|---------------|------------|
| `STORAGE_BACKEND` | `registry.get_object_storage()` | `minio` | `s3` |
| `MINIO_ENDPOINT` | `MinIOStorageProvider` | `http://minio:9000` | N/A |
| `MINIO_ACCESS_KEY` | `MinIOStorageProvider` | `minioadmin` | N/A |
| `MINIO_SECRET_KEY` | `MinIOStorageProvider` | `minioadmin` | N/A |
| `MINIO_BUCKET` | `MinIOStorageProvider` | `studyai` | `studyai-prod` |
| `S3_BUCKET` | `S3StorageProvider` | N/A | Required |
| `S3_ACCESS_KEY` | `S3StorageProvider` | N/A | Required |
| `S3_SECRET_KEY` | `S3StorageProvider` | N/A | Required |
| `OCR_PROVIDER_CHAIN` | `registry.get_ocr_provider()` | `tesseract,mock` | `google,mock` |
| `LLM_PROVIDER_CHAIN` | `registry.get_llm_provider()` | `ollama,mock` | `openai,mock` |
| `OLLAMA_BASE_URL` | `OllamaLLMProvider` | `http://ollama:11434` | N/A |
| `LLM_MODEL` | `OllamaLLMProvider` | `llama3.1:8b` | `gpt-4o-mini` |
| `EMBEDDING_PROVIDER` | `registry.get_embedding_provider()` | `sentence_transformers` | `openai` |
| `EMBEDDING_MODEL_NAME` | `SentenceTransformerEmbeddingProvider` | `all-MiniLM-L6-v2` | N/A |
| `EMBEDDING_DEVICE` | `SentenceTransformerEmbeddingProvider` | `auto` | `cpu`/`cuda` |
| `EMAIL_BACKEND` | `registry.get_email_provider()` | `mailpit` | `smtp` |
| `MAILPIT_HOST` | `MailpitEmailProvider` | `mailpit` | N/A |
| `SMTP_HOST` | `SMTPEmailProvider` | N/A | Required |

---

## Test Coverage Traceability

| Test File | Protocols Tested | Providers Tested | Scenarios |
|-----------|------------------|------------------|-----------|
| `test_providers.py` | All 5 | Mock, Console, Hashing, LocalObjectStorage | Contracts, selection, invalid config, switching |
| `test_ocr.py` | `OCRProvider` | Mock, Tesseract, PaddleOCR | Deterministic output, chain fallback, failure handling |
| `test_llm.py` | `LLMProvider` | Mock, Ollama | All prompt types, chain fallback, injection directive, sanitization |
| `test_embeddings.py` | `EmbeddingProvider` | Hashing, SentenceTransformer | Dimension, normalization, batch, version mismatch, backfill |
| `test_storage.py` | `ObjectStorageProvider` | Local, MinIO | CRUD, presigned URLs, existence, size |
| `test_email.py` | `EmailProvider` | Console, Mailpit, SMTP | Send, password reset, multipart, captured emails |
| `test_backup.py` | N/A | MinIO backup/restore | Backup commands, offsite hook, separate storage config |

---

## Docker Service Traceability

| Service | Image | Ports | Healthcheck | Depended By |
|---------|-------|-------|-------------|-------------|
| `db` | `pgvector/pgvector:pg16` | 5432 | `pg_isready` | api, worker, beat |
| `redis` | `redis:7-alpine` | 6379 | `redis-cli ping` | api, worker, beat |
| `minio` | `minio/minio:latest` | 9000, 9001 | `curl /minio/health/live` | api, worker, beat |
| `mailpit` | `axllent/mailpit:latest` | 1025, 8025 | `wget /` | api, worker, beat |
| `ollama` | `ollama/ollama:latest` | 11434 | `ollama list` | api, worker, beat |
| `api` | `./backend` | 8000 | `curl /healthz` | frontend |
| `worker` | `./backend` | — | — | — |
| `beat` | `./backend` | — | — | — |
| `frontend` | `./frontend` | 80 | `wget /nginx-health` | — |

---

## Dependency Traceability

| Package | Purpose | Providers Using |
|---------|---------|-----------------|
| `tesserocr>=2.6.0` | Tesseract OCR bindings | `TesseractOCRProvider` |
| `sentence-transformers>=3.0` | Local embeddings | `SentenceTransformerEmbeddingProvider` |
| `boto3>=1.34` | MinIO/S3 client | `MinIOStorageProvider`, `S3StorageProvider` |
| `ollama>=0.3` | Ollama client (unused, using requests) | `OllamaLLMProvider`, `OllamaChatProvider` |
| `paddleocr` (optional) | PaddleOCR | `PaddleOCRProvider` |
| `django-cors-headers` | CORS | Already in Phase 10 |
| `django-redis` | Redis cache | Already in Phase 10 |
| `django-prometheus` | Metrics | Already in Phase 10 |

---

## Security Traceability

| Security Feature | Implementation | Test |
|------------------|----------------|------|
| Credential isolation | All secrets via env vars | `test_providers.py` invalid config tests |
| Fail-fast production | Registry raises `ValueError` | `test_providers.py::test_s3_missing_credentials`, `test_openai_missing_credentials` |
| No silent fallback | Chain explicit in env vars | `test_providers.py::test_provider_switching` |
| Prompt injection defense | `LLMChainProvider` prepends directive | `test_llm.py::test_llm_chain_adds_prompt_injection_directive` |
| PII sanitization | `LLMChainProvider` regex redaction | `test_llm.py::test_llm_chain_sanitizes_user_input` |
| Audit logging | `ProviderCallLog` in chains | `test_llm.py`, `test_ocr.py` chain fallback tests |