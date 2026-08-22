# StudyAI — Engineering Documentation

Documentation of the **actual implementation** in this repository, built against the v4.1 architecture spec (`StudyAI_app_architecture_v4_1_full.md`).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phase 1 (security foundation) of 8 phases is implemented — roughly 10% of the full v4.1 scope.** Everything not yet built is documented as such; no scaffolding is counted as a feature.

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** — the mandatory module-by-module audit.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI 3.0 spec (authoritative API contract) |
| **architecture/** | |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, structure, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A-001…) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Implemented flows (Mermaid) |
| **setup/** | |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| **backend/** | |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | Actual tables, constraints, RLS, ER diagram |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security model + isolation enforcement points |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job model & state machine (no workers yet) |
| **frontend/** | |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | IndexedDB/outbox scaffold; fencing status |
| **modules/** | |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — ❌ not implemented |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — ❌ not implemented |
| **ai/** | |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Pipeline stages & providers (none configured) |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval design — all stages missing |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Metrics — none currently measured |
| **operations/** | |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging implemented; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle of existing data |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented — stated plainly |

## Repository layout

```text
StudyAI/
├── StudyAI_app_architecture_v4_1_full.md   # authoritative architecture spec (v4.1)
├── backend/                                 # Django 6.1 + DRF API
├── frontend/                                # React 19 PWA (Vite + TypeScript)
├── myenv/                                   # central Python virtualenv (3.14)
├── docs/phase_1/                            # this documentation set
├── .env.example                             # placeholder-only env template
└── .gitignore
```

## Quick start

```bash
# prerequisites: PostgreSQL 18 running, Node ≥ 20
createdb studyai 2>/dev/null;

cd backend && ../myenv/bin/pip install -r requirements.txt
../myenv/bin/python manage.py migrate
../myenv/bin/python manage.py runserver          # http://127.0.0.1:8000

cd ../frontend && npm install && npm run dev     # http://localhost:5173
```
