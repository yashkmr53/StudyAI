# StudyAI — Phase 8 Documentation (Production Hardening) & Final System Audit

Engineering documentation for the repository state **after Phase 8** — the final phase of the v4.1 implementation order.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented |
| 🟡 | Simplified / alternative implementation |
| 🔧 | Mocked / stubbed |
| ❌ | Not implemented |

**Overall: all 8 phases implemented — ~70% of full v4.1 scope structurally realized.** Phase 8 closes the hardening gaps: LLM provider fallback chain, health/status/metrics endpoints, rate limiting, security headers + magic-byte upload sniffing, audit logging with staff listing, daily AI budget enforcement (graceful degradation), backup/restore commands with a **performed and verified drill**, an evaluation regression gate, a CI pipeline, Docker/deploy artifacts, and a load-test baseline that passes §75 targets.

## Honest headline

Everything mechanical is real. What remains synthetic or unexercised is explicit: OCR/LLM *content* is mock-generated; verifier thresholds and mastery/planner constants are uncalibrated; eval datasets are empty; scheduled backup automation and cloud deployment have not been executed. Each is tracked in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

Start here: **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** — includes the final whole-system audit.

## Documentation map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Feature audit incl. final whole-system audit |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Remaining gaps w/ next steps |
| [CHANGELOG.md](CHANGELOG.md) | Phase 8 changes |
| [openapi.yaml](openapi.yaml) | Final generated OpenAPI spec |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Full-system architecture status |
| [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md) | 111-row requirement → code → test → status matrix |
| [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md) | H-series hardening decisions |
| [architecture/SYSTEM_FLOWS.md](architecture/SYSTEM_FLOWS.md) | Ops flows (health/metrics/backup/fallback) |
| [setup/LOCAL_SETUP.md](setup/LOCAL_SETUP.md) | From clean checkout to running system |
| [setup/ENVIRONMENT_AND_SECRETS.md](setup/ENVIRONMENT_AND_SECRETS.md) | Env vars, secret rules |
| [setup/CREDENTIALS_AND_ACCESS.md](setup/CREDENTIALS_AND_ACCESS.md) | External services & credentials |
| [setup/DEPLOYMENT.md](setup/DEPLOYMENT.md) | Compose stack now authored; caveats |
| [backend/DATABASE_SCHEMA.md](backend/DATABASE_SCHEMA.md) | Audit/provider-log tables; cumulative RLS |
| [backend/API.md](backend/API.md) | All endpoints incl. health/status/audit |
| [backend/AUTHENTICATION_AND_SECURITY.md](backend/AUTHENTICATION_AND_SECURITY.md) | Security review outcome |
| [backend/BACKGROUND_JOBS.md](backend/BACKGROUND_JOBS.md) | Registry unchanged; ops hooks |
| [frontend/OFFLINE_SYNC.md](frontend/OFFLINE_SYNC.md) | Unchanged |
| [modules/NOTE_SPACE.md](modules/NOTE_SPACE.md) · [modules/AI_CLASSROOM.md](modules/AI_CLASSROOM.md) | Module final states |
| [ai/AI_PIPELINE.md](ai/AI_PIPELINE.md) · [ai/RAG_AND_RETRIEVAL.md](ai/RAG_AND_RETRIEVAL.md) · [ai/AI_EVALUATION.md](ai/AI_EVALUATION.md) | AI reality check |
| [operations/TESTING.md](operations/TESTING.md) | 116 tests; commands; gaps |
| [operations/OBSERVABILITY.md](operations/OBSERVABILITY.md) | Endpoints + metrics implemented |
| [operations/TROUBLESHOOTING.md](operations/TROUBLESHOOTING.md) | Symptom → cause → fix |
| [operations/DATA_LIFECYCLE.md](operations/DATA_LIFECYCLE.md) · [operations/BACKUP_AND_RECOVERY.md](operations/BACKUP_AND_RECOVERY.md) | Drill performed |
| [../scripts/load_test.py](../../scripts/load_test.py) | Stdlib-only load harness + §75 gate |

Phase 1–7 documentation: [`../phase_1/`](../phase_1/README.md) … [`../phase_7/`](../phase_7/README.md).

## Quick start

```bash
brew install pgvector 2>/dev/null; brew services restart postgresql@18
createdb studyai 2>/dev/null || true
./myenv/bin/pip install -r backend/requirements.txt
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
curl -s http://127.0.0.1:8000/readyz
```
