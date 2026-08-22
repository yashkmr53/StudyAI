# StudyAI — Phase 6 Documentation (AI Classroom Intelligence)

Engineering documentation for the repository state **after Phase 6** (Phases 1–6 of the v4.1 implementation order complete).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: Phases 1–6 of 8 complete (~52% of full v4.1 scope).** Phase 6 delivers the AI Classroom intelligence layer: generated-layer models (EnrichedNote/Block/CitationBlock), a versioned prompt registry, schema-validated enrichment pipeline stages A–F, a real rules-based evidence verifier with per-citation verdicts, enrichment API endpoints with ai-stale propagation and forced refresh, and a runnable evaluation harness.

## Honest headline

The pipeline machinery — retrieval-grounded drafting, gap detection/filling from READY reference books, citation stitching, evidence verification with independent provenance, idempotent scheduling, stale propagation — is real and tested. The **text generation itself comes from a 🔧 mock LLM** (deterministic restructuring of supplied evidence); a real model swap is a registry change. The verifier thresholds are uncalibrated placeholders pending labeled data.

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit with statuses, tests, gaps |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Every incomplete/mocked/missing piece |
| [CHANGELOG.md](CHANGELOG.md) | Dated implementation changes |
| [openapi.yaml](openapi.yaml) | Generated OpenAPI spec incl. enrich/enrichment/refresh-ai |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Layers, modules, invariants w/ status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | Requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | Decision log (A-/B-/C-/D-/E-/F-series) |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Enrichment pipeline flow (Mermaid) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Dev vs staging vs production reality |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | Generated-layer tables + RLS |
| [backend/API.md](backend/API.md) | Every implemented endpoint |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security incl. AI-layer isolation |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Job registry incl. enrich jobs |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Canvas sync (unchanged this phase) |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) | Module 1 — ✅ complete |
| [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module 2 — foundation + intelligence status |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) | Full stage-by-stage reality |
| [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) | Retrieval (unchanged this phase) |
| [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | Harness implemented; datasets empty |
| [operations/TESTING.md](operations/TESTING.md) | Commands, counts, gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Logging; metrics planned |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) | Lifecycle incl. enriched notes |
| [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Not implemented |

Phase 1–5 documentation: [`../phase_1/`](../phase_1/README.md) … [`../phase_5/`](../phase_5/README.md).

## Quick start

```bash
createdb studyai 2>/dev/null;
cd backend && ../myenv/bin/pip install -r requirements.txt
../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
# POST /api/v1/documents/{id}/enrich → GET /api/v1/documents/{id}/enrichment
```
