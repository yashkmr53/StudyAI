# Known Limitations

Every incomplete, partial, mocked, stubbed, simplified, or missing piece — with impact and next step.

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | RLS enforcement | Policies exist; dev role is superuser ⇒ bypassed locally | §3: RLS as second isolation layer | No behavioral enforcement test; prod role undefined | Isolation currently rests on app layer alone | Create non-superuser role; add enforcement tests; wire into prod settings |
| 2 | Rate limiting | Absent | §23/§61 `429 RATE_LIMITED` | No throttles anywhere | Brute-force/abuse exposure once public | DRF throttle classes on auth endpoints first |
| 3 | Password reset | 🔧 Stub returns 202 always | §23 password reset flow | No email backend, no reset tokens | Users cannot recover accounts | Add token model + email dispatch in hardening phase |
| 4 | Token storage (frontend) | localStorage | Secure refresh handling | XSS would expose tokens | Medium; standard trade-off | Consider httpOnly cookie refresh + CSRF handling pre-launch |
| 5 | Object storage serving | ⚠️ Signed URLs generated; **no views serve them** | §23 private storage + short-lived URLs | Upload/download routes missing | Storage unusable by flows | Build storage views + validation in Phase 3 |
| 6 | Background jobs | ✅ model/claim semantics; ❌ no tasks/workers/reaper/backoff | §19 durable jobs | Nothing async runs | Blocks Phases 3–7 features | Install Redis; define OCR task + reaper with Phase 3 |
| 7 | Celery broker | Configured URL to non-existent Redis | §2 Redis broker | Redis not installed | Harmless until tasks exist | `brew install redis` at Phase 3 start |
| 8 | Canvas (models/API/UI) | ❌ Placeholder route only | §4–5 canvas + fencing | Everything | Core input path missing | Phase 2: models → API → drawing UI |
| 9 | Offline sync transport | 🔧 Outbox logic w/o `send` wiring; `client_sequence`=timestamp | §4 outbox sync | No endpoints; sequence ties possible | Sync unproven end-to-end | Wire flush to canvas API; monotonic counter |
| 10 | Ingestion/OCR/canonical docs | ❌ | §6 | All of it | Blocks both product modules | Phase 3 |
| 11 | NoteSpace PDF | ❌ | §7/§49 | Renderer, artifacts, endpoints | Module 1 absent | Phase 4 |
| 12 | AI Classroom (all) | ❌ skeletons only | §8–18 | Chunking→chat everything | Module 2 absent | Phases 5–7 |
| 13 | pgvector / tsvector | Extension not installed | §14 hybrid retrieval | No vector/FTS capability | Blocks retrieval | Install extension with Phase 5 migrations |
| 14 | Provider implementations | 🔧 Registry raises NotImplementedError | §24 provider layer | No OCR/LLM/embedding/storage-cloud impls | External capabilities absent | Select providers (spec §30) per phase |
| 15 | Health endpoints | ❌ | ops readiness | None | Can't monitor liveness | Add `/healthz`, `/readyz` before any deploy |
| 16 | Audit logging | ❌ app skeleton | §23 admin audit trail | None | Compliance gap | Implement with Phase 8 |
| 17 | Observability metrics/alerts/tracing | ❌ request-ID logging only | §25 | No metrics/emitters | Blind operations | Instrument jobs/providers as they land |
| 18 | Backups/DR | ❌ none; no RPO/RTO | §70 | Nothing automated | Data-loss risk | Pre-production blocker; see BACKUP_AND_RECOVERY.md |
| 19 | CI pipeline | ❌ tests run locally only | engineering hygiene | No automated gate | Regression risk | GitHub Actions: backend tests (PG service) + frontend build/test |
| 20 | Deployment artifacts | ❌ prod settings only | §24 compose stack | No Dockerfile/compose/nginx | Cannot deploy | Author compose stack when staging is scheduled |
| 21 | OpenAPI completeness | ⚠️ spec generates with 3 warnings (plain APIViews lack serializer hints) | §30 OpenAPI authoritative | Request schemas inferred poorly for 3 views | Minor doc drift risk | Add `@extend_schema` annotations |
| 22 | Coverage measurement | ❌ not measured | hygiene | Unknown coverage % | Blind spots possible | Add `coverage run manage.py test` to CI |

## Deliberate deviations (not defects)

- Trailing-slash-less URLs, 422 validation remap, JSON-only renderer, page-number pagination — all recorded in [architecture/ASSUMPTIONS_AND_DECISIONS.md](architecture/ASSUMPTIONS_AND_DECISIONS.md).
- `Job.profile_id` without FK constraint (A-015).
- Profile DELETE endpoint exists though §60 omits it (superset, harmless).
