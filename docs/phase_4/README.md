# StudyAI — Phase 4 Documentation (NoteSpace)

Engineering documentation for the repository state **after Phase 4** (Phases 1–4 of the v4.1 implementation order complete).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phases 1–4 of 8 complete (~37% of full v4.1 scope).** Phase 4 delivers Module 1 end-to-end: layout-aware PDF rendering that preserves transcribed content verbatim, immutable content-addressed DigitizedDocument artifacts, async render jobs through the durable job runtime, authorization-gated signed downloads, and the NoteSpace frontend (upload → OCR → review/edit → generate/download PDF).

## Honest headline

The typed-PDF pipeline is real and faithful to whatever transcription exists — but the transcription itself still comes from 🔧 mock OCR until a real handwriting provider lands (§30). The renderer provably adds and removes nothing (see [operations/TESTING.md](operations/TESTING.md)).

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI spec incl. digitized-documents |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A-/B-/C-/D-series) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Implemented flows (Mermaid) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | Tables incl. digitizeddocument + RLS |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security model + isolation points |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job registry incl. pdf_render |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Canvas sync (unchanged this phase) |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — now ✅ with stated boundaries |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — ❌ not started |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Pipeline status (OCR mocked) |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval — all stages missing |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Metrics — none measured |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging implemented; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle incl. PDF artifacts |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented |

Phase 1–3 documentation: [`../phase_1/`](../phase_1/README.md), [`../phase_2/`](../phase_2/README.md), [`../phase_3/`](../phase_3/README.md).

## Quick start

```bash
createdb studyai 2>/dev/null;
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
# open http://localhost:5173/notespace → upload a page image → Generate PDF
```
