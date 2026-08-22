# Architecture Gap Analysis — StudyAI v4.1

Date: 2026-08-22
Source of truth: `StudyAI_app_architecture_v4_1_full.md` (architecture v4.1, §1–80)
Method: code-level verification of every backend app (`models`, `urls`, `services`),
`providers/`, `shared/`, `frontend/src/`, tests, compose/CI configuration — cross-checked
against the architecture's model specs (§6/§7/§9/§10/§15/§17/§18/§19/§29/§66), endpoint
blueprint (§60), error contract (§61), service boundaries (§65), provider protocols (§64),
cross-cutting requirements (§21/§23–§26/§69–§75) and Definition of Done (§77).

Supersedes stale claims in `docs/phase_9_production_readiness/FINAL_IMPLEMENTATION_STATUS.md`
where code has since moved on (rate limiting and audit logging are implemented and tested;
that scorecard predates them). `KNOWN_LIMITATIONS.md` items were re-verified individually.

---

## 1. Implemented and verified

Auth + JWT rotation/blacklist · RLS (24 policies over 24 tables, transaction-local GUC,
worker context propagation) · canvas fencing (generation/heartbeat/takeover → 409
SESSION_LOCK_LOST) · client IndexedDB outbox with per-stroke idempotency keys · canonical
Document/DocumentPage/DocumentPageRevision/DocumentLine layer · NoteSpace PDF pipeline
(fpdf2, immutable artifacts, signed downloads) · chunking + hybrid retrieval (pgvector +
tsvector + RRF, READY-gated reference chunks) · enrichment pipeline A–F with EvidenceVerifier ·
stable tags + TagChangeLog + MasteryScore · revision-aware questions · adaptive tests +
EMA mastery + atomic attempt grading · profile/subject-scoped chat with provenance ·
deterministic revision planner · durable Job state machine (atomic claim, exponential
backoff + jitter, dead-letter, cancel API) · daily AI budget → 429 RATE_LIMITED with
NoteSpace unaffected · evaluation harness runners + `--assert-gte` regression gate ·
backup_database / verify_backup commands (manual drill succeeded) · auth throttling
(LiveSettingsScopedRateThrottle, opt-in test coverage) · audit logging (AuditLog,
ProviderCallLog) · healthz/readyz/status endpoints · full §61 error envelope (12 codes) ·
OpenAPI via drf-spectacular + Swagger UI · all 10 §66 database constraints · 116 green
tests on Docker PostgreSQL/pgvector.

---

## 2. Missing / not implemented

### A. Go-live blockers

| # | Item | Evidence |
|---|---|---|
| A1 | Real OCR provider | Only `MockOCRProvider` (+ chain); all transcribed content fabricated (§30 open decision) |
| A2 | Real LLM provider | Only `MockLLMProvider`/`FailingLLM`; enrichment/questions/chat answers synthetic |
| A3 | RLS enforcement under deployment role | App connects as superuser ⇒ PostgreSQL exempts it from RLS; behavioral probe proven only via `SET ROLE`; restricted role never wired into prod config |
| A4 | Scheduled backup automation | Commands exist; nothing schedules them; no offsite copy; no documented RPO/RTO |

### B. Backend features / models / endpoints

| # | Item | Spec ref | Status |
|---|---|---|---|
| B1 | Notebooks module | §60 CRUD | `apps/notebooks/` empty stub — no model/views/urls |
| B2 | `GET /api/v1/documents/{id}/questions` | §60 | Questions exist; no per-document listing endpoint |
| B3 | Password reset completion | §23 | Endpoint always 202; no token model, no email dispatch |
| B4 | Tag rename REST endpoint | §18 | Rename service exists in `tagging.py`; no route |
| B5 | Server-side `SyncOperation` model | §4/§16 | Replaced by stroke-level idempotency (documented deviation); client outbox exists in IndexedDB |
| B6 | Standalone `Embedding` model | §9 | Embedded directly on NoteChunk |
| B7 | Enrichment coalescing window + change-magnitude threshold | §21 | Any edit → new job; dedup is content-hash equality only |
| B8 | Monthly provider budget, per-job cost cap, token accounting | §74 | Daily call-count proxy only; ProviderCallLog lacks input/output token fields |
| B9 | Neural embedding provider | §2 | Hashing embedder only (lexical-grade; CJK untokenized) |
| B10 | S3-compatible object storage | §23/§64 | Local FS only; registry rejects other backends |
| B11 | Raw-upload retention policy + object storage GC | §69 | Superseded PDFs/orphaned uploads accumulate indefinitely |
| B12 | Profile deletion/anonymization flow | §69 | Not implemented |
| B13 | `ProviderError` (502) exception class | §61 | Mapping-only; never raised |
| B14 | Canvas finalize returns 200, not 202 + job resource | §22 | Minor contract deviation |

### C. Scheduling & operations

| # | Item | Evidence |
|---|---|---|
| C1 | No scheduler anywhere | Zero `beat_schedule`/cron/PeriodicTask in repo → reaper (`reap_stuck_jobs`) and retry promotion never run automatically |
| C2 | Backup schedule/offsite/RPO-RTO | See A4 |
| C3 | Full-stack compose E2E drill on clean host | Never executed end-to-end incl. worker broker round-trip |
| C4 | TLS termination | nginx has no HTTPS server block; no certificate provisioning |
| C5 | External monitoring/alerting | No Prometheus/Grafana/Sentry/PagerDuty wiring |

### D. Security hardening

| # | Item | Spec ref | Status |
|---|---|---|---|
| D1 | CORS configuration | §23 | Absent entirely (works today only because SPA is same-origin behind nginx) |
| D2 | CSRF_TRUSTED_ORIGINS | §23 | Not configured |
| D3 | Distributed throttle cache | §23 | LocMemCache = per-process counters; multi-worker/multi-node counters independent |
| D4 | Prompt-injection instructions inside prompts | §72 | Evidence wrapped structurally (EVIDENCE_JSON) but no explicit untrusted-content directives; untested vs real LLM |
| D5 | Data-minimization filter before provider calls | §73 | Implicit size bounds only; no redaction layer |
| D6 | CSP header | §23 | Absent (nosniff/Referrer-Policy present) |

### E. Observability gaps (vs §25)

OCR fallback rate (hardcoded `None`) · schema-validation-failure counter · retrieval
latency metric · evaluation trend surface · product usage metrics · persistent time-series
store (in-memory deque resets on process restart).

### F. Evaluation & calibration (§26)

| # | Item |
|---|---|
| F1 | Golden dataset: zero cases authored (need ~30–50 representative notes + labeled retrieval/citation/question/chat cases) |
| F2 | Evidence-verifier thresholds uncalibrated (supported ≥0.60 / partial ≥0.30 are arbitrary defaults) |
| F3 | Mastery EMA constants and planner weights untuned engineering guesses |
| F4 | OCR CER/WER/confidence-calibration evaluation absent while OCR is mocked |

### G. Frontend

| # | Item | Status |
|---|---|---|
| G1 | AI Classroom UI | Placeholder stub |
| G2 | Tests UI | Placeholder stub |
| G3 | Chat UI | Placeholder stub |
| G4 | Revision planner UI | Placeholder stub |
| G5 | Offline detection (online/offline events) | Missing |
| G6 | Service-worker Background Sync plugin | Missing (in-app timers only) |
| G7 | Outbox `sending/failed/retrying` transitions | Defined in schema, never written (only pending→acknowledged) |
| G8 | Generated OpenAPI client | Hand-typed fetch wrappers |
| G9 | `hooks/`, `state/`, `services/storage/` structure | Not per §63 (minor; zustand stores inline) |

### H. Quality / tooling

No coverage measurement tooling · load testing done only at small local scale
(§75 targets met locally) · CI workflow authored but never executed on GitHub ·
no CI check that the committed OpenAPI snapshot matches generated schema.

---

## 3. Deliberate deviations from spec letter (documented decisions, not defects)

Sequential pipeline functions instead of LangGraph dependency · `revision_ids[]` JSON list
instead of singular FK on EnrichedNote/DigitizedDocument · signed-URL JSON payload instead
of HTTP redirect on download · call-count budget proxy until real provider pricing exists ·
local-FS storage for v1 · hashing embeddings as deterministic placeholder · trailing-slash-less
URLs matching §60 exactly · DRF 400 remapped to 422 per §61 · stroke-level idempotency keys
instead of server-side SyncOperation table · canvas finalize synchronous 200.

---

## 4. §77 Definition-of-Done scoreboard

27 checklist items: **21 satisfied** · 🟡 **3 partial** (offline robustness G5–G7 · backup
automation A4/C2 · observably active E) · ❌ **3 open** (real-provider product value A1/A2 ·
evaluation suite against agreed thresholds F1/F2 · production backup/restore test).

---

## 5. Required inputs & where they go

| # | Input needed | Owner decision / credential | Lands in |
|---|---|---|---|
| 1 | Handwriting OCR provider choice (§30.1) | Vendor name + API key | `.env` `OCR_API_KEY` (reserved); impl `backend/providers/ocr/<name>.py`; registry wiring |
| 2 | LLM provider choice (§30.6) | Vendor + key + model names | `.env` `LLM_API_KEY` (reserved); impl `backend/providers/llm/<name>.py` behind `LLMChainProvider` |
| 3 | Neural embedding model decision | Model name/path | `.env` `EMBEDDING_MODEL_PATH` (reserved); impl `backend/providers/embeddings/`; bump `EMBEDDING_MODEL_VERSION` + backfill plan |
| 4 | Object storage endpoint | Bucket, region, credentials | New `.env` `S3_*` vars; impl `backend/providers/storage/s3.py`; flip `OBJECT_STORAGE_BACKEND=s3` |
| 5 | Email service for password reset | SMTP host/port/credentials or dev-console backend | `.env` `EMAIL_*` vars; `PasswordResetToken` model in `apps/accounts/`; complete view |
| 6 | Non-superuser DB role policy (A3) | Approval to split migrator vs app roles | Migration + compose/prod env changes; re-run behavioral RLS probe through Django connection |
| 7 | Scheduler preference | Celery Beat (recommended) vs system cron | `config/celery.py` `beat_schedule` (reaper, retry promotion, backups); optional `beat` compose service |
| 8 | Hosting target + domain (§30.2) | VM provider, domain name, cert approach | `deploy/nginx.conf` HTTPS block; TLS env; deploy docs |
| 9 | Monitoring preference | Sentry DSN / Prometheus endpoint / defer | `.env` keys; `shared/observability` exporter |
| 10 | Golden evaluation data | ~30–50 notes + human labels (query→expected chunks; claim→evidence→support status) | Scaffold format at `backend/apps/evaluation/datasets/`; runner + gate already built |
| 11 | Product decisions (§30 remainder) | Raw-OCR retention window; allow user-edit-before-AI; change-threshold %; launch subject scope; citation calibration approach | Env-driven settings + small migrations/services |
| 12 | Frontend priority order | ai-classroom / tests / chat / revision | `frontend/src/features/<module>/` + routes |
| 13 | Tooling approvals | yes/no each | `coverage.py` + CI step; `django-cors-headers` + `CSRF_TRUSTED_ORIGINS`; Redis-backed throttle cache swap |

## 6. Implementable immediately (no inputs required)

B1/B2/B4 missing endpoints · B7 coalescing window (tunable default) · B8 token columns +
monthly-budget scaffolding · B13 exception class · C1 scheduler wiring · C2 local backup
automation + offsite hook stub · D1/D2/D4/D5/D6 security hardening · E metric additions ·
G5–G7 frontend offline hardening · H coverage tooling + OpenAPI drift check in CI.

Blocked purely on inputs above: **A1–A4**, B3 (email creds), B9/B10 (choices), C4
(domain/TLS), F1 (labeled data).

## 7. Suggested execution order

1. Scheduler + backup automation + security hardening (no inputs needed)
2. Missing backend endpoints/models (B-batch)
3. Real provider integrations once vendors chosen (A1/A2/B9/B10)
4. Golden dataset authoring + verifier/mastery/planner calibration (F)
5. Frontend modules (G1–G4)
6. TLS/hosting + clean-host compose drill + production-scale load test (C3/C4)

Nothing in this document has been implemented yet; it is the agreed gap ledger.
