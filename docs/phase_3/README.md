# StudyAI — Phase 3 Documentation (Shared Ingestion)

Engineering documentation for the repository state **after Phase 3** (Phases 1–3 of the v4.1 implementation order complete). Builds directly on Phase 1 (security foundation) and Phase 2 (canvas/offline).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phases 1–3 of 8 complete (~30% of full v4.1 scope).** Phase 3 delivers the shared ingestion layer: canonical Document/Page/Revision/Line models, signed-URL upload flow with file validation, logical OCR jobs with primary→fallback provider chain, full job state machine runtime (dispatch, retry/backoff, dead-letter, reaper, jobs API), OCR review/edit creating immutable new revisions, and the §67 canvas-finalize→ingestion transaction.

## Honest headline

The OCR providers are 🔧 **mocks** — the real handwriting provider is an explicitly open decision (spec §30). Everything *around* the provider is real: durable jobs, idempotency, fallback mechanics, review states, RLS-scoped worker execution, and storage round-trips.

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI 3.0 spec incl. documents/jobs/storage |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A-/B-/C-series) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Implemented flows (Mermaid) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | Tables, constraints, RLS, ER diagram |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security model + isolation points |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job runtime as actually built |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Canvas offline sync (unchanged this phase) |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — ❌ renderer still pending |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — ❌ not started |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Pipeline: OCR stage mocked, rest absent |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval — all stages missing |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Metrics — none measured |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging implemented; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle incl. documents/images/jobs |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented |

Phase 1/2 documentation: [`../phase_1/`](../phase_1/README.md), [`../phase_2/`](../phase_2/README.md).

## Quick start

```bash
createdb studyai 2>/dev/null;
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
# Optional broker-free worker: ../myenv/bin/python manage.py process_jobs --reap
```
