# StudyAI — Phase 5 Documentation (AI Classroom Foundation)

Engineering documentation for the repository state **after Phase 5** (Phases 1–5 of the v4.1 implementation order complete).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phases 1–5 of 8 complete (~45% of full v4.1 scope).** Phase 5 delivers the AI Classroom foundation: the NoteChunk source layer, revision-aware incremental chunking, local embeddings, pgvector dense search + PostgreSQL full-text fused with Reciprocal Rank Fusion, READY-gated reference-book ingestion through the canonical layer, and a search API to exercise it all.

## Honest headline

The retrieval pipeline is real — pgvector HNSW index, GIN full-text index, RRF fusion, profile scoping, incremental re-indexing on edits. The **embedding provider is a simplified local hashing embedder** (🟡), not a neural model; semantic quality is therefore lexical-grade until a proper local model is adopted. OCR upstream remains 🔧 mocked.

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI spec incl. /search |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A-/B-/C-/D-/E/F-series) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Implemented flows (Mermaid) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | NoteChunk/references schema, vector+FTS indexes, ERD |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security model + retrieval isolation |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job registry incl. index jobs |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Canvas sync (unchanged this phase) |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — ✅ complete |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — foundation done, intelligence pending |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Pipeline incl. chunk/embed stage detail |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval as actually built |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Metrics — none measured |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging implemented; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle incl. chunks/embeddings |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented |

Phase 1–4 documentation: [`../phase_1/`](../phase_1/README.md) … [`../phase_4/`](../phase_4/README.md).

## Quick start

```bash
brew install pgvector                       # one-time; extension for dense search
createdb studyai 2>/dev/null;
cd backend && ../myenv/bin/pip install -r requirements.txt
../myenv/bin/python manage.py migrate        # creates pgvector extension + indexes
../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
```
