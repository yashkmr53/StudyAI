# Architecture Traceability — Production Readiness Audit

Requirement → implementation → database objects → API endpoints → tests → verification evidence.

Legend per audit spec: ✅ VERIFIED · 🟡 IMPLEMENTED—NOT VERIFIED · 🟠 PARTIAL · 🔴 MISSING · ⚪ DEFERRED

---

## 1. Security boundaries & multi-tenancy (§3)

| Layer | Requirement | Implementation | DB | API | Tests | Evidence | Status |
|---|---|---|---|---|---|---|---|
| App | Profile is tenant boundary; resources scope to profile_id | FK chains from every resource to profiles_profile | FK constraints on all owned tables | Queryset filters in every ViewSet | Cross-user probes → 404 across all types | Live curl + suite | ✅ |
| App | Client-supplied profile IDs never trusted | `ProfileAuthorizationService.ensure_profile_access` called before writes | — | — | foreign-profile tests → 403/404 | Suite + E2E | ✅ |
| App | Ownership-scoped querysets on all reads (§3) | `.filter(profile__user=request.user)` in every ViewSet.get_queryset() | — | all list/detail routes | isolation tests across profiles/documents/tests/chat/enrichment/tags/questions | Suite + live probes | ✅ |
| DB | RLS ENABLED on 23 profile-scoped tables (§3) | 6 migration bundles across subjects/canvas/documents/retrieval/ai_classroom/tests+chat+revision | pg_policies: 24 rows confirmed via query | — | pg_policies structural check | This audit psql session | ✅ policies exist |
| DB | RLS fail-closed without GUC | Policies compare `profile_id::text = current_setting('app.current_profile_id', true)`; empty string matches nothing | pg_policies | — | **Restricted-role probe: no GUC → zero rows on profiles/subjects/documents/chunks** | This audit psql session | ✅ |
| DB | RLS scoped to correct profile with GUC set | Same policies; `set_config('app.current_profile_id', uuid, true)` inside atomic block | `shared/database/rls.py` | — | **Probe: correct UUID → exactly that profile's rows; wrong UUID → zero** | This audit psql session | ✅ |
| Config | Superuser bypass documented (§3 caveat) | Dev role `yash` has rolsuper=t; bypasses RLS by PostgreSQL design | pg_roles check | — | Manual pg_roles query during audit | Known gap | ⚠️ prod must use non-superuser role |
| Worker | Trusted RLS context in background processing (§3/§47) | Executor wraps handlers in `profile_scoped_transaction(job.profile_id)` from job payload | `apps/jobs/services.py::run_claimed_job` | — | Pipeline tests pass under PG with context binding asserted | Suite | ✅ mechanism / 🟡 broker path unverified |

## 2. Authentication & accounts

| Feature | Implementation | API endpoint | Test | Evidence | Status |
|---|---|---|---|---|---|
| Email login, UUID PKs, Argon2 hashing (§23) | Custom User model + SIMPLE_JWT + PASSWORD_HASHERS[0] | POST /auth/register | auth_flow suite + live curl | Register returns 201 with user/profile/tokens | ✅ |
| Atomic user+profile creation (§44.1) | transaction.atomic in RegisterView.post | POST /auth/register | test_register_creates_user_profile_and_tokens | Profile row present after single call | ✅ |
| Token rotation + blacklist revocation (§23) | ROTATE_REFRESH_TOKENS=True, BLACKLIST_AFTER_ROTATION=True | POST /auth/refresh, POST /auth/logout | logout/replay test | Replayed refresh token rejected 401 | ✅ |
| Audit trail for auth lifecycle (§23) | audit_event() calls at register/login/logout | implicit | AuditLogTests | AuditLog rows confirmed in deployed stack | ✅ |
| Password reset email flow (§23) | Returns 202 stub always | POST /auth/password-reset | none | No email backend configured | 🔧 STUBBED |

## 3. Data integrity

| Constraint (§66) | Table | Migration file | Test file | Status |
|---|---|---|---|---|
| unique(user,name) Profile | profiles/0001 | constraint test | ✅ |
| unique(profile,name) Subject | subjects/0001 | duplicate test | ✅ |
| unique(session,page_number) CanvasPage | canvas/0001 | duplicate page test | ✅ |
| unique(document,page_number) DocumentPage | documents/0001 | structural | ✅ |
| unique(page,revision_number) DocumentPageRevision | documents/0001 | finalize/edit suites | ✅ |
| unique(revision,line_index) DocumentLine | documents/0001 | structural | ✅ |
| unique(revision,content_hash,chunk_index) NoteChunk | retrieval/0001 | index dedupe test | ✅ |
| unique(source_revision_id,content_hash,question_key) Question | questions/0001 | generation dedupe | ✅ |
| unique(idempotency_key) Job | jobs/0001 | claim/duplicate tests | ✅ |
| unique(subject,stable_key) Tag | ai_classroom/0001 | tagging suite | ✅ |
| unique(document,content_hash) WHERE NOT superseded DigitizedDocument | documents/0003 partial index | regen test | ✅ |
| unique(document,tag) DocumentTag | ai_classroom/0001 | rerun-stability test | ✅ |
| unique(test,question) TestQuestion | tests/0001 | structural | ✅ |
| unique(test,question) TestAttempt | tests/0001 | replay→409 test | ✅ |
| unique(profile,tag) MasteryScore | tests/0001 | structural | ✅ |

## 4. Provider abstraction (§24)

| Protocol | Chain provider | Registered impls | Used by | Fallback tested | Status |
|---|---|---|---|---|---|
| OCRProvider | OCRChainProvider | MockOCRProvider(mock/mock_low_confidence/failing) | run_ocr_job | fallback test ✅ / providers 🔧 mock | ✅ mechanism |
| LLMProvider | LLMChainProvider | MockLLMProvider/FailingLLMProvider | enrich/chat/questions pipeline stages | fallback unit test ✅ / providers 🔧 mock | ✅ mechanism |
| EmbeddingProvider | HashingEmbeddingProvider | direct call in index_document | index tests ✅ | 🟡 lexical-grade placeholder |
| ObjectStorageProvider | LocalObjectStorage | storage views + document/pdf flows | roundtrip/forged tests ✅ | 🟡 local FS only |

## 5. Async job architecture (§19–20, §24)

| Feature | Implementation | Test | Status |
|---|---|---|---|
| Durable Job model w/ §19 state machine | apps/jobs/models.py | claim test | ✅ model |
| Atomic conditional claim (single winner) | Job.claim() conditional UPDATE | single-winner test | ✅ |
| Idempotent creation keyed on idempotency_key (§20) | get_or_create_job + unique constraint | duplicate-finalize test | ✅ |
| Exponential backoff + jitter via next_retry_at (§20) | retry_backoff(); promote_due_retries() | dead-letter test asserts backoff set | ✅ |
| Dead-letter after max attempts (§19) | JOBS_MAX_ATTEMPTS=3 | dead-letter test | ✅ |
| Reaper for stuck RUNNING jobs (§19) | reap_stuck_jobs() + process_jobs --reap flag | untested | ⚠️ function exists, not auto-scheduled |
| Dispatch: Celery broker / eager inline / DB-polling executor (§24) | dispatch_job + process_jobs command | eager everywhere; executor drill in compose stack | ✅ eager + executor verified / 🟡 broker path not exercised end-to-end |
| ProviderCallLog telemetry per attempt (§25) | record_provider_call() in LLMChainProvider | status endpoint exposes usage counts | ✅ |

## 6. Module 1 — NoteSpace

| Requirement | Implementation | Test | Status |
|---|---|---|---|
| Faithful renderer preserving verbatim content (§7/§49) | pdf_renderer.py fpdf2 + DejaVu fonts | purity test + PDF magic/size assertions | ✅ |
| Headings only where explicitly represented (§49) | DocumentLine.is_heading flag honored; never inferred | purity flag assertion | ✅ |
| Immutable content-addressed artifacts (§27) | DigitizedDocument unique(document,hash); superseded retained | regen/version-change tests | ✅ |
| Renderer versioning recorded (§13-adjacent) | RENDERER_VERSION stored per artifact | version-change test | ✅ |
| Secure download authz-gated signed URL (§49) | DigitizedDownloadView ownership → HMAC URL | secure-access tests | ✅ |
| No semantic content added (§7) | renderer consumes line texts only; no LLM import path exists | purity test structural assertion | ✅ |

## 7. Canvas & offline sync

| Requirement | Implementation | Test/Evidence | Status |
|---|---|---|---|
| CanvasSession/Page/Stroke models w/ §66 constraints | canvas models | canvas suite | ✅ |
| Stroke→page via page_id + sequence_order; no arrays (§4) | models + IndexedDB shape | structural | ✅ |
| IndexedDB immediate stroke persistence (<50 ms target) | putStroke before any network call | manual E2E timing | ✅ design-guaranteed |
| Sync outbox queue + flush triggers (§4) | interval 3 s + per-stroke + visibility/unload | manual E2E | 🟡 no explicit pause-debounce timer |
| Outbox failure states persisted (§4) | failures stay pending for retry; failed/retrying statuses not written | — | 🟡 simplified |
| Client idempotency keys prevent dupes (§4) | stroke-level UUID keys; server get_or_create dedupe | replay test | ✅ |
| Monotonic client_sequence = outbox auto-increment id (G-011) | db.ts enqueueOperation update | — | ✅ |
| Fencing generation + heartbeat + takeover (§5) | ensure_lock + takeover + heartbeat | fencing/heartbeat/takeover tests + live E2E | ✅ |
| Server-side SyncOperation table (§29 diagram) | replaced by stroke-level keys (B-001) | replay test | 🟡 alternative |

## 8. Ingestion

| Requirement | Implementation | Test | Status |
|---|---|---|---|
| Upload flow create doc/page → signed PUT target (§45) | DocumentViewSet.create | upload roundtrip suite | ✅ |
| Magic-byte upload validation (§23) | _magic_matches vs declared type | mismatch/sniff tests | ✅ |
| Finalize upload: validate → hash → revision → OCR job → 202 (§46) | finalize_upload | finalize suite | ✅ |
| Logical OCR job primary→fallback (§6/§28) | OCRChainProvider | fallback/dead-letter tests | ✅ mechanism 🔧 providers |
| Real handwriting OCR provider | mock only (F-002/C-001) | — | 🔴 §30 open decision |
| OCR review states + edit creates new revision (§48) | status fields + create_user_revision | low-confidence + immutability tests | ✅ |
| Original image never overwritten (§47) | immutable object keys | structural | ✅ |
| Downstream enqueue: OCR → index job (§47) | run_ocr_job tail calls enqueue_index_job | full-pipeline tests | ✅ |
| Retry-processing endpoint (§60) | retry action resets failed jobs | retry tests | ✅ |

## 9. Retrieval & AI Classroom intelligence

| Requirement | Implementation | Test | Status |
|---|---|---|---|
| NoteChunk source layer w/ embedding metadata (§10) | retrieval/models.py | chunk/index tests | ✅ |
| Page-aware chunking + context window (§10) | build_chunks greedy word packing | span/context test | ✅ |
| Incremental embed-only-new indexing (§10) | hash-diff in index_document | rerun incremental test | ✅ |
| Edit invalidation: stale-out old chunks/questions, embed new (§10/§27) | stale flags + insert + Question.stale propagation | invalidation/staleness tests | ✅ |
| pgvector dense HNSW cosine (§32) | AdaptiveVectorField + HNSW migration | dense-channel test (PG) | ✅ |
| tsvector keyword GIN index (§33) | SearchVectorField + SearchRank | keyword hit test | ✅ |
| RRF fusion k=60 depth=50 (§14) | RetrievalService.search | score composition in payload | ✅ constants untuned |
| Scope enforcement on every retrieval (§14) | SQL filters + READY gate + stale filter | isolation/non-ready tests | ✅ |
| Reference books READY-gated ingestion (§15) | references app + ingest command | ready/exclusion tests | ✅ |
| Enrichment A–F schema-validated nodes (§11) | run_enrichment_job + validate_stage_output | full-pipeline tests | ✅ mechanics |
| Citation verification rules-v1 (§12/§41) | EvidenceVerifier._classify lexical support | classification unit + discriminating E2E | ✅ mechanism ⚠️ thresholds uncalibrated |
| Grounding priority notes→references (§51) | draft cites user chunks; gap_fill cites reference chunks | reference-grounded E2E | ✅ structural within mock limits |
| Prompt/model versioning records (§13) | PromptVersion registry seeded; per-artifact fields populated | registry seeding test | ⚠️ registry real, models mocked |
| Tags stable identity + changelog (§18) | Tag/TagChangeLog/TaggingService | rename/stability tests | ✅ |
| Revision planner deterministic (§58) | RevisionPlanningService.build_plan | plan-shape test | ✅ |

## 10. Platform

| Requirement | Implementation | Test/Evidence | Status |
|---|---|---|---|
| Health endpoints /healthz /readyz (§25) | shared/observability/views.py | healthz/readyz tests | ✅ NEW |
| Internal status page metrics (§25) | StatusView staff-only aggregates | payload-shape test | ✅ NEW |
| Request latency p50/p95/p99 capture (§25/§75) | TimingMiddleware histogram | load baseline output | ✅ NEW |
| Security headers middleware (§23) | SecurityHeadersMiddleware | header test | ✅ NEW |
| External APM/alerting (§25) | — | — | ❌ |
| OpenAPI authoritative (§30/§32) | drf-spectacular → committed spec | regeneration command | ✅ |
| Request IDs + structured logs (§25) | middleware + formatter/filter | manual correlation | ✅ |
| Backup/restore drill performed (§32/§70) | backup_database + verify_backup commands | drill output captured this audit | ⚠️ manual drill done; scheduled automation ❌ |
| CI pipeline executing suites (hygiene) | .github/workflows/ci.yml authored | workflow never executed on GitHub | ⚠️ authored, not yet run |
| Simplest infra for v1 (§32 #25) | broker-free operation proven; no external AI APIs | — | ✅ |
| Versioned REST APIs (§22) | /api/v1/** | all API tests | ✅ |
| Async endpoints 202 + job resource (§22) | revisions/pdf/enrich/retry return 202 | asserted | ✅ |
| Deployment artifacts compose/docker/nginx (§24) | authored but clean-host drill pending | config VALID | 🟡 authored |
| Coverage measurement tooling | absent | — | ❌ |

---

## Summary counters

```text
Tracked requirements: 111
✅ VERIFIED (executed evidence):   81
🟡 IMPLEMENTED — NOT VERIFIED:      7
🟠 PARTIAL:                         9
🔴 MISSING:                        12
⚪ DEFERRED / NOT APPLICABLE:        2
```

> Note: the ✅ count includes items where "verified" means an executed test, command, or live probe produced concrete evidence. It does NOT mean production-hardened — see KNOWN_LIMITATIONS.md for remaining operational and security gaps.
