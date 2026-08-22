# StudyAI — Phase 7 Documentation (Learning Features)

Engineering documentation for the repository state **after Phase 7** (Phases 1–7 of the v4.1 implementation order complete).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phases 1–7 of 8 complete (~60% of full v4.1 scope).** Phase 7 delivers the learning layer: stable tag hierarchy with change log, revision-aware question generation, deterministic adaptive test assembly, attempt grading wired to a shared mastery scoring service, an evidence-grounded chatbot with verified citations, and the deterministic revision planner.

## Honest headline

All *machinery* is real — stable tag identity, stale-aware questions, transactional attempts + EMA mastery, profile-scoped chat citations, deterministic planning. The content quality still depends on 🔧 mock OCR and 🟡 hashing embeddings, and the mock LLM generates questions/answers by restructuring evidence rather than reasoning.

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI spec incl. tests/chat/revision |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A- through G-series) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Learning-loop flows (Mermaid) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | New tables, constraints, RLS |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security incl. chat/mastery isolation |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job registry status |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Canvas sync (unchanged this phase) |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — ✅ |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — learning layer now ✅ w/ caveats |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Pipeline incl. question/chat stages |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval consumed by chat/planner |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Harness runnable; datasets still empty |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle incl. attempts/goals |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented |

Phase 1–6 documentation: [`../phase_1/`](../phase_1/README.md) … [`../phase_6/`](../phase_6/README.md).

## Quick start

```bash
createdb studyai 2>/dev/null;
cd backend && ../myenv/bin/pip install -r requirements.txt
../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
# Enrich a document → POST /tests → answer → GET /revision/overview
```
