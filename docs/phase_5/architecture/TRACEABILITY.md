# Traceability — Phase 5 state

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile is tenant boundary (§3) | FKs on all owned resources; chunks carry nullable profile (platform rows NULL) | isolation suites | ✅ |
| Client-supplied profile IDs never trusted (§3) | `shared/authorization/services.py` + scoped querysets everywhere | foreign-access tests | ✅ |
| App-layer authorization on all queries (§3) | per-ViewSet/queryset filtering incl. search scoping | isolation tests | ✅ |
| RLS on profile-scoped tables (§3) | migrations across subjects/canvas/documents/retrieval (10 tables) | pg_policies manual check | ⚠️ superuser bypasses locally |
| Transaction-local RLS context (§3/§47) | `shared/database/rls.py` executor binding | GUC/no-leak tests | ✅ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | envelope assertions | ✅ |
| File type/size validation (§23) | storage upload view | validation tests | ✅ |
| Rate limiting (§23) | — | — | ❌ |
| Audit logging (§23) | skeleton only | — | ❌ |

## Authentication

Unchanged from Phase 4: mature JWT+Argon2 auth ✅ · atomic registration ✅ · revocation strategy ✅ · password reset 🔧 stub · no sensitive logging ✅. See [`../phase_1/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_1/backend/AUTHENTICATION_AND_SECURITY.md).

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| §66 unique constraints (all prior + NoteChunk triple) | migrations incl. `retrieval/0001` | suites | ✅ |
| Durable jobs w/ atomic claim (§19) | `apps/jobs/models.py` + services | claim test | ✅ |
| Idempotency keys live: OCR, PDF, index (§20) | keys module + index key format | duplicate-request tests | ✅ |
| Canonical models + immutable revisions (§6/§48) | `apps/documents/models.py`, services | immutability tests | ✅ |
| NoteChunk source layer with page ranges/hashes/embedding metadata (§10) | `apps/retrieval/models.py` | chunk/index tests | ✅ |
| revision_ids list generalizing singular field (§10 shape) | JSONB column (E-002) | structural | 🟡 deviation recorded |
| Source vs generated separation (§9) | chunks are pure source; PDFs generated; AI-generated layer absent yet | structural | 🟡 by phase order |
| Historical artifacts retained (§27) | stale chunks retained; superseded PDFs retained | stale-retention test | ✅ |
| Tags with stable identity (§18) | — | — | ❌ |

## Canvas & offline

Unchanged from Phase 2 audit ([`../phase_4/architecture/TRACEABILITY.md`](../architecture/TRACEABILITY.md)): fencing ✅, heartbeat/takeover ✅, finalize transaction incl. ingestion ✅, outbox core ✅ (failure states 🟡), flush triggers 🟡.

## Ingestion → indexing pipeline

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Shared ingestion layer (§6) | `IngestionService` + storage views | upload/canvas suites | ✅ |
| Upload flow w/ signed targets + validation (§45–46) | documents API + storage views | upload suite | 🟡 local-FS stand-in for S3 |
| Logical OCR job primary→fallback (§6/§28) | chain provider + idempotent jobs | fallback/dead-letter tests | ✅ mechanism / 🔧 providers |
| OCR review states + user-edit revisions (§48) | status fields + create_user_revision | edit/immutability tests | ✅ |
| Original image never overwritten (§47) | immutable object keys | structural | ✅ |
| Worker flow: RLS context + atomic lines (§47) | `run_ocr_job` under executor scope | pipeline tests | ✅ |
| **Downstream enqueue after OCR → index job** | `run_ocr_job` tail | E2E auto-index smoke | ✅ |
| Retry-processing + Jobs API (§60) | actions/views | retry + jobs API tests | ✅ |
| Async endpoints return 202 + job (§22) | revisions/pdf/retry | asserted | ✅ |

## AI Classroom foundation (Phase 5 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Page-aware chunking w/ context window (§10) | `build_chunks` greedy word packing + carried overlap | span/context test | ✅ |
| Incremental diff indexing; embed only new/changed (§10) | hash-diff in `index_document`; stats counters | incremental rerun test | ✅ |
| Edit invalidation: stale-out old, index new, retain history (§10/§27) | stale flag + insert path | invalidation test | ✅ |
| Local embeddings, no external dependency (§2/§31-31) | hashing uni+bigram embedder, L2-normalized | determinism tests | 🟡 lexical-grade only |
| Embedding model/version stored per chunk (§10) | columns populated at embed time | assertions | ✅ |
| pgvector dense channel w/ HNSW cosine index (§32) | AdaptiveVectorField + HNSW migration | dense-channel test (PG) | ✅ |
| PostgreSQL full-text w/ GIN index (§33) | SearchVectorField + SearchRank | keyword hit test | ✅ |
| Reciprocal Rank Fusion over both channels (§14) | k=60 fusion in RetrievalService.search | score composition in payload | ✅ |
| Optional reranking stage (§14) | explicitly optional for v1 | — | ❌ not needed yet |
| Scope enforcement: profile/subject/source/status on every retrieval (§14) | SQL filters + READY gate + stale filter | isolation/non-ready tests | ✅ |
| ReferenceBook/Chapter models (§15) | `apps/references/models.py` | ingestion tests | ✅ |
| Reference ingestion through canonical layer → READY (§15) | `manage.py ingest_reference_book` command | ready/retrievable tests | ✅ admin-command path |
| Users cannot modify reference content (§15) | no write endpoints; profile-scoped listing hides them | structural | ✅ |
| READY gating in retrieval (§15) | join filter + read-time defensive check | non-ready exclusion test | ✅ |
| Search endpoint to exercise retrieval | `POST /api/v1/search` (F-004 extension) | api + E2E | ✅ |

## NoteSpace / platform remainder

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| NoteSpace faithful renderer/PDFs/artifacts/download (§7/§49) | complete since Phase 4 | note-space suite | ✅ |
| Canvas rasterization for OCR input (§6) | stdlib PNG writer | unit test | 🟡 simplified |
| Generation ⊥ provenance fields (§12) | ocr_provider/edited_by recorded | structural | 🟡 early fields |
| Prompt/model versioning (§13) | embedding_model/version live; prompt dataclasses stubs | — | 🔧 partial |
| Enrichment pipeline A–F (§11) | — | — | ❌ |
| Citation verification (§12) | — | — | ❌ |
| Chatbot scoping (§16) | — | — | ❌ |
| Adaptive tests (§17/§55) | — | — | ❌ |
| MasteryScoringService (§18) | — | — | ❌ |
| Coalescing/quota-aware LLM (§21/§74) | — | — | ❌ |
| Evaluation harness (§26) | — | — | ❌ |
| Provider fallback chains — LLM side (§28) | protocol exists | — | ❌ n/a until LLM |
| Provider abstraction; SDKs isolated (§24) | protocols + registry incl. embeddings | structural | ✅ interfaces |
| Private storage + short-lived signed URLs (§23) | local variant end-to-end | roundtrip tests | 🟡 local variant |
| OpenAPI authoritative (§30/§32) | regenerated per phase | — | ✅ |
| Request IDs + structured logs (§25) | middleware + logs incl. index stats | manual | ✅ |
| Metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32) | — | — | ❌ |
| Simplest infra for v1 (§32 #25) | broker-free; no external embedding APIs | — | ✅ |
| Versioned REST APIs (§22) | `/api/v1/**` | all suites | ✅ |

## Counters

```text
Tracked requirements: 87
✅ 52   ⚠️ 3   🟡 6   🔧 3   ❌ 23
```
