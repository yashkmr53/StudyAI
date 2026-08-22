# Architecture

Actual architecture of the repository as built, mapped to v4.1 spec sections.

## Product modules

| Module | Purpose | Status |
|---|---|---|
| NoteSpace (Module 1) | Canonical document → typed PDF, faithful only | ❌ [modules/NOTE_SPACE.md](../modules/NOTE_SPACE.md) |
| AI Classroom (Module 2) | Enrichment, tags, tests, chat, revision | ❌ [modules/AI_CLASSROOM.md](../modules/AI_CLASSROOM.md) |
| Shared foundation (auth, profiles, subjects, jobs, errors, RLS) | Phase 1 security foundation | ✅ |

## Implemented stack

| Layer | Technology | Version | Where |
|---|---|---|---|
| API framework | Django + DRF | 6.1 / DRF 3.x | `backend/` |
| Auth | djangorestframework-simplejwt | 5.x | `config/settings/base.py` |
| Database | PostgreSQL (Homebrew) | 18 | dev: socket `/tmp`, db `studyai` |
| DB driver | psycopg (binary) | 3.x | `backend/requirements.txt` |
| Schema/API docs | drf-spectacular | 0.28+ | `/api/schema/`, `docs/phase_1/openapi.yaml` |
| Async (configured, unused) | Celery | 5.x | `config/celery.py` |
| Frontend | React + TypeScript + Vite | 19 / 5.9 / 7.x | `frontend/` |
| PWA | vite-plugin-pwa (Workbox) | 1.x | `frontend/vite.config.ts` |
| Client state | zustand | 5.x | `src/features/auth/authStore.ts` |
| Local storage | idb (IndexedDB wrapper) | 8.x | `src/db/indexeddb/db.ts` |
| Python env | `myenv/` (central venv) | Python 3.14 | repo root |

## Backend structure (as built)

```text
backend/
├── manage.py
├── config/
│   ├── settings/{base,dev,test,prod}.py
│   ├── urls.py            # /admin, /api/schema, /api/docs, /api/v1
│   ├── celery.py          # configured; no tasks defined yet
│   └── wsgi.py
├── apps/
│   ├── accounts/          # ✅ User + auth endpoints
│   ├── profiles/          # ✅ Profile model + ViewSet + router
│   ├── subjects/          # ✅ Subject model + ViewSet + RLS migration
│   ├── jobs/              # ✅ Job model (no producers)
│   └── notebooks/ canvas/ documents/ ingestion/ notespace/
│       ai_classroom/ retrieval/ questions/ tests/ chat/
│       revision/ references/ evaluation/ audit   # 🔧 empty skeletons
├── providers/
│   ├── base.py            # ✅ 4 protocols (§64)
│   ├── registry.py        # 🔧 NotImplementedError stubs
│   └── storage/local.py   # ⚠️ signed-URL generation; no serving views
├── shared/
│   ├── authorization/services.py   # ✅ ownership checks
│   ├── database/rls.py             # ✅ transaction-local GUC helpers
│   ├── exceptions/handlers.py      # ✅ §61 envelope
│   ├── idempotency/keys.py         # ✅ §20 key formats
│   └── observability/request_id.py # ✅ middleware + log filter
└── tests/{unit,integration,api,e2e}/
```

## Frontend structure (as built)

```text
frontend/src/
├── app/            # App shell + global styles
├── routes/         # route table + RequireAuth guard
├── features/auth/  # LoginPage, RegisterPage, authStore (zustand)
├── components/     # Layout (sidebar nav), Placeholder
├── services/api/   # client.ts (fetch, refresh-retry), auth.ts
├── services/sync/  # outbox.ts (queue/flush)
├── db/indexeddb/   # db.ts (strokes + outbox stores)
├── types/          # api.ts (User, Profile, Subject, ApiError)
└── utils/          # idempotency.ts (mirrors backend key format)
```

Note: `hooks/` and `state/` from spec §63 do not exist yet — state currently lives in `features/auth/authStore.ts`. This is intentional until a second store justifies the directories.

## Request pipeline

```text
Request → SecurityMiddleware → Session → Common → CSRF → Auth → Messages
        → XFrameOptions → RequestIDMiddleware (assigns req_<hex>)
        → URL resolver → DRF view
        → JWTAuthentication → permission check → handler
        → shared.exceptions.handlers.exception_handler (on error)
        → JSON response (+ X-Request-ID header)
```

## Invariants honored (spec §32/§79 subset relevant so far)

| Invariant | How it holds today |
|---|---|
| PostgreSQL is durable source of truth | All state in Postgres; Redis unused |
| RLS context is transaction-local | `set_config(..., true)` inside `atomic()` only |
| App authorization + RLS both enforce isolation | Queryset filtering + policies |
| Provider SDKs isolated behind interfaces | `providers/base.py`; zero SDK imports in apps |
| OpenAPI is authoritative contract | Generated from code; committed at `docs/phase_1/openapi.yaml` |
| Simplest infra for v1 | No ES, no cloud deps, local FS storage |
| Every async job idempotent | Unique `idempotency_key`; atomic claim (semantics tested) |

Invariants concerning OCR/canonical documents/AI artifacts are not yet exercisable — no such code exists ([TRACEABILITY.md](TRACEABILITY.md) tracks each).
