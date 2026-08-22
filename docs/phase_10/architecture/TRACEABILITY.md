# Traceability — Phase 10

**Date:** 2026-08-23

---

## Gap Analysis → Implementation Mapping

| Gap ID | Description | Implementation | Tests |
|--------|-------------|----------------|-------|
| **C1** | No scheduler anywhere | `backend/config/celery.py` `beat_schedule` + `docker-compose.yml` beat service | Logs show task execution |
| **C2/A4** | Backup schedule/offsite/RPO-RTO | `backup_database`/`verify_backup` commands + `scripts/backup_offsite_hook.sh` + runbook | Manual drill succeeds |
| **D1** | CORS configuration | `django-cors-headers`, `CORS_ALLOWED_ORIGINS`, middleware order | Headers on responses |
| **D2** | CSRF_TRUSTED_ORIGINS | Setting + env var | Cross-origin POST works |
| **D3** | Distributed throttle cache | `CACHES['throttle']` = `django-redis` on DB 2 | Keys in Redis DB 2 |
| **D4** | Prompt-injection directives | `LLMChainProvider` prepends directive | In `ProviderCallLog.input_payload` |
| **D5** | Data-minimization filter | `_sanitize_for_provider()` with regex + truncation | `redactions_count` in metadata |
| **D6** | CSP header | `SecurityHeadersMiddleware` | `Content-Security-Policy` header |
| **B1** | Notebooks module | `apps/notebooks/` (models, views, urls, admin, RLS) | 17 tests passing |
| **B2** | Document questions endpoint | `DocumentQuestionsViewSet` at `/documents/{id}/questions` | 4 tests passing |
| **B4** | Tag rename REST endpoint | `TagViewSet.rename` action at `/tags/{id}/rename/` | 6 tests passing |
| **B7** | Enrichment coalescing | `enqueue_enrichment()` window + magnitude + `coalesced_from` FK | Logic verified |
| **B8** | Token columns + monthly budget | `UserProfile` budget fields, `BudgetService`, `AIBudgetThrottle` | 429 on budget exceed |
| **B13** | ProviderError exception | `ProviderError` (502) raised by chains | 502 envelope on 5xx |
| **E** | Observability metrics | `/metrics` endpoint with Prometheus counters/histograms | `curl /metrics` works |
| **G5** | Online/offline detection | `useOnlineStatus` hook + `OfflineBanner` | UI shows on disconnect |
| **G6** | SW Background Sync | `public/sw.js` with `backgroundSync` | SW registers, syncs on reconnect |
| **G7** | Outbox state transitions | `pending→sending→acknowledged / failed→retrying→sending` | Zustand store tracks counts |
| **H** | CI tooling | `.github/workflows/ci.yml` with coverage + OpenAPI drift | Pipeline passes |

---

## Architecture Spec → Implementation Trace

| Architecture § | Component | Phase 10 Changes |
|----------------|-----------|------------------|
| §2 | Redis broker | Throttle cache on DB 2 |
| §4 | Client outbox | SW background sync, state transitions |
| §11 | Enrichment pipeline | Coalescing window + magnitude |
| §18 | Tag system | Rename endpoint |
| §19 | Job state machine | `coalesced_from` FK |
| §21 | Budget enforcement | Monthly budget + throttle |
| §23 | Security hardening | CORS, CSRF, Redis throttle, CSP, prompt-injection, data-minimization |
| §25 | Observability | Prometheus metrics endpoint |
| §28 | Provider chains | Prompt-injection, data-minimization, ProviderError |
| §60 | API endpoints | Notebooks, document questions, tag rename |
| §61 | Error contract | `PROVIDER_ERROR` → 502 |
| §63 | Frontend structure | `hooks/`, `components/`, `state/` added |
| §69 | Data lifecycle | Backup runbook with RPO/RTO |
| §70 | Backup/restore | Offsite hook stub + runbook |
| §72 | Prompt injection | Directive in LLM chain |
| §73 | Data minimization | Filter in provider chain |
| §74 | Budget/cost accounting | Token fields in ProviderCallLog |
| §75 | Testing | CI coverage gates |
| §77 | Definition of Done | 27 items addressed |

---

## Code Coverage Mapping

| Module | Coverage Target | Status |
|--------|-----------------|--------|
| `apps.notebooks` | ≥80% | ✅ New tests cover CRUD + RLS |
| `apps.questions` | ≥80% | ✅ New tests cover endpoint |
| `apps.ai_classroom` | ≥80% | ✅ New tests cover tag rename |
| `shared.observability` | ≥80% | ✅ Metrics helpers tested indirectly |
| `shared.throttles` | ≥80% | ✅ Budget throttle tested via integration |
| `providers.llm` | ≥80% | ✅ Chain logic tested via enrichment |

---

## Security Control Trace

| Control | Implementation | Verification |
|---------|----------------|--------------|
| CORS | `django-cors-headers` | `Access-Control-Allow-Origin` header |
| CSRF | `CSRF_TRUSTED_ORIGINS` | Cross-origin POST succeeds |
| Rate Limiting | Redis throttle cache | Keys in Redis DB 2 |
| Prompt Injection | System prompt directive | In `ProviderCallLog` |
| Data Minimization | Regex redaction + truncation | `redactions_count` logged |
| CSP | `SecurityHeadersMiddleware` | `Content-Security-Policy` header |
| Budget Enforcement | `AIBudgetThrottle` | 429 with budget details |

---

## Performance Baselines

| Metric | Target | Phase 10 Baseline |
|--------|--------|-------------------|
| Backup duration | < 30 min | N/A (depends on DB size) |
| Coalescing check | < 10 ms | Added to `enqueue_enrichment` |
| Budget check | < 5 ms | Added to throttle |
| Prompt sanitization | < 2 ms | Regex + truncation |
| Metrics endpoint | < 10 ms | In-process counters |

---

## Rollback Trace

Each component can be rolled back independently per `PHASE_10_IMPLEMENTATION_PLAN.md` Rollback Plan. All migrations are reversible (except budget fields which may lose data).

---

## Future Trace (Phase 11)

| Input | Depends On | Phase 11 Impact |
|-------|------------|-----------------|
| OCR provider (A1) | Vendor choice | Replace `MockOCRProvider` |
| LLM provider (A2) | Vendor + key | Replace `MockLLMProvider` |
| Embedding model (B9) | Model choice | Replace hashing embedder |
| S3 storage (B10) | Bucket + creds | Implement `S3StorageProvider` |
| Email (B3) | SMTP creds | Complete password reset |
| DB role (A3) | DBA approval | Non-superuser app role |
| TLS (C4) | Domain + cert | nginx HTTPS block |
| Golden data (F1) | Human labels | Calibrate verifier/planner |