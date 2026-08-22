# Changelog

## [0.2.0] — 2026-08-22 — Documentation restructure & audit

| Field | Detail |
|---|---|
| Change | Replaced flat numbered docs with structured engineering documentation set (`architecture/`, `setup/`, `backend/`, `frontend/`, `modules/`, `ai/`, `operations/` + root status/limitations/changelog); added requirement→code→test traceability matrix; generated committed `openapi.yaml`; placeholders-only `.env.example` |
| Reason | Documentation must describe actual implementation with per-feature status classification, not intentions |
| Files affected | `docs/phase_1/**` (all new), `.env.example`, `docs/phase_1/openapi.yaml` (generated) |
| Database migration | none |
| API impact | none |
| Breaking changes | none |

Audit outcome recorded in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md): 19 ✅ / 3 ⚠️ / 1 🟡 / 5 🔧 / 30 ❌ across 58 tracked requirements.

## [0.1.0] — 2026-08-21 — Phase 1: Security Foundation

| Field | Detail |
|---|---|
| Change | Initial implementation of v4.1 Phase 1 + foundational pieces for later phases |
| Reason | First increment of the 8-phase implementation order (spec §31) |
| Files/modules affected | `backend/config/**`, `apps/{accounts,profiles,subjects,jobs}`, `shared/**`, `providers/**`, `backend/tests/**`, `frontend/**` (full scaffold), `.env.example`, `.gitignore`, `backend/requirements.txt` |
| Database migration | accounts 0001 · profiles 0001 · subjects 0001 + 0002_enable_rls · jobs 0001 (+ Django/SimpleJWT built-ins) |
| API impact | Added `/api/v1/auth/{register,login,logout,refresh,password-reset}`, `/api/v1/profiles[/{id}]`, `/api/v1/subjects[/{id}]`, `/api/schema/`, `/api/docs/` |
| Breaking changes | n/a (initial) |

Details:

- Backend: email-based custom User (UUID PK), Profile/Subject models with §66 unique constraints, JWT auth with rotation+blacklist, §61 error envelope (DRF validation → 422), RLS policies + transaction-local context helpers, durable Job model with atomic claim and unique idempotency keys, provider protocols + local signed-URL storage provider, request-ID middleware + structured logging, OpenAPI via drf-spectacular, skeletons for all remaining domain apps.
- Frontend: Vite + React 19 + TS PWA scaffold, auth feature (pages + zustand store + persisted tokens), fetch client with refresh-retry and typed error envelope, IndexedDB strokes/outbox stores, outbox queue/flush service, route guard + layout.
- Verification: backend suite green on SQLite (15 pass, 2 skip) and PostgreSQL (17 pass); end-to-end smoke through the Vite proxy; frontend build + vitest green.
