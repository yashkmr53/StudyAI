# Changelog

## [0.9.0] — 2026-08-22 — Phase 8: Production Hardening (final implementation phase)

| Field | Detail |
|---|---|
| Change | Implemented Phase 8 hardening (§31 items 50–55 + deferred ops items): LLM fallback chain, health/status/metrics endpoints, request timing, rate limiting, security headers, magic-byte sniffing, audit logging + staff listing, daily AI budget enforcement, eval regression gate, backup/verify commands with performed drill, CI workflow, Docker/compose/nginx artifacts, load-test harness + baseline |
| Reason | Final phase of the implementation order; closes §23/§25/§26/§28/§70/§75 hardening items that were deferred from earlier phases |
| Files/modules affected | `backend/apps/audit/**` (models/services/views/command/migrations), `backend/providers/llm/{chain,failing,mock}.py`, `backend/apps/{ai_classroom,chat,documents}/**` (chain wiring, budgets, throttle scopes), `shared/throttles.py`, `shared/observability/{metrics,views}.py`, `config/settings/{base,dev,test,ci}.py`, `config/urls.py`, `.github/workflows/ci.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `deploy/nginx.conf`, `backend/scripts/load_test.py`, `docs/phase_8/**` |
| Database migration | audit 0001_initial |
| API impact | Added `/healthz`, `/readyz` (public), `/api/v1/status` (staff), `/api/v1/audit?action=` (staff); 429 RATE_LIMITED now reachable via throttles and AI budget; X-Duration-Ms response header |
| Breaking changes | none |

### Hardening delivered

- LLMChainProvider primary→fallback with per-attempt ProviderCallLog telemetry; registry chain settings-driven; unified result shape with attempted_providers.
- Scoped throttles (auth 30/min, ai 120/min) behind live-settings class + global enable flag; verified 429 envelope.
- SecurityHeadersMiddleware; magic-byte sniffing for uploads (422 on mismatch).
- AuditLog service + staff listing; events: register/login/logout/document.created.
- Daily AI budget per profile → graceful 429 degradation while NoteSpace stays available.
- Status page aggregates: job queue depth/dead-letters/retryable backlog, provider usage, citation verdict distribution, request percentiles.
- Eval regression gate (`--assert-gte`) exiting non-zero on metric regressions.

### Ops

- Backup drill executed: pg_dump → verify_backup restore into scratch DB → row counts matched.
- Load baseline captured with stdlib harness: all scenarios p95 < 500 ms vs §75 targets.
- CI workflow authored (Postgres service backend suite + frontend build/test).

## [0.8.0] — Phase 7 · earlier
See [`../phase_7/CHANGELOG.md`](../phase_7/CHANGELOG.md).
