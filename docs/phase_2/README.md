# StudyAI — Phase 2 Documentation (Canvas & Offline)

Engineering documentation for the repository state **after Phase 2** of the v4.1 implementation order. Built on top of the Phase 1 security foundation.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phases 1–2 of 8 complete (~20% of full v4.1 scope).** Phase 2 delivers the canvas domain end-to-end: models, fenced single-writer API, offline-first drawing UI, IndexedDB persistence, and a working sync outbox with server-side idempotent replay protection.

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**.

## What Phase 2 added

- `CanvasSession` / `CanvasPage` / `CanvasStroke` models with §66 constraints and RLS policies.
- Canvas API: sessions, pages, batched idempotent strokes, heartbeat, takeover, finalize — with real `409 SESSION_LOCK_LOST` fencing and `409 REVISION_CONFLICT` immutability.
- Frontend drawing editor: pointer-event ink on `<canvas>`, strokes persisted to IndexedDB immediately, background sync via grouped outbox flushes, 25 s heartbeats, takeover banner.
- Outbox transport: per-page batching, monotonic `client_sequence` (outbox auto-increment id), lock-lost propagation.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI 3.0 spec incl. canvas endpoints |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A-/B-series) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Implemented flows (Mermaid) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | Tables, constraints, RLS, ER diagram |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security model + isolation points |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job model (still no workers) |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Offline architecture as actually built |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — ❌ not implemented |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — ❌ not implemented |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Pipeline stages (none configured) |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval design — all stages missing |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Metrics — none currently measured |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging implemented; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle incl. canvas data |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented — stated plainly |

Phase 1 documentation remains at [`../phase_1/`](../phase_1/README.md).

## Quick start

```bash
createdb studyai 2>/dev/null;
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev    # http://localhost:5173 → Canvas tab
```
