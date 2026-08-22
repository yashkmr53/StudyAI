# Architecture — after Phase 2

Repository state following Phases 1–2 of the v4.1 implementation order.

## Product modules

| Module | Purpose | Status |
|---|---|---|
| NoteSpace (Module 1) | Canonical document → typed PDF | ❌ Phase 4 |
| AI Classroom (Module 2) | Enrichment, tags, tests, chat, revision | ❌ Phases 5–7 |
| Canvas + offline sync (input layer) | Handwriting capture, autosave, fenced sync | ✅ Phase 2 |
| Security foundation | Auth, profiles/subjects, errors, RLS | ✅ Phase 1 |

## Implemented stack

| Layer | Technology | Where |
|---|---|---|
| API framework | Django 6.1 + DRF | `backend/` |
| Auth | SimpleJWT (rotation + blacklist), Argon2 | `config/settings/base.py` |
| Database | PostgreSQL 18 (UUID PKs, RLS on 5 tables) | dev: socket `/tmp`, db `studyai` |
| Schema docs | drf-spectacular → `openapi.yaml` | `/api/schema/` |
| Async (configured, unused) | Celery 5.x | `config/celery.py` |
| Frontend | React 19 + TypeScript + Vite 7 PWA | `frontend/` |
| Client state | zustand (auth + canvas stores) | `src/features/*/​*Store.ts` |
| Local storage | idb — strokes + outbox stores | `src/db/indexeddb/db.ts` |
| Drawing | HTML5 Canvas 2D, pointer events | `src/features/canvas/CanvasEditor.tsx` |

## Backend structure additions (Phase 2)

```text
apps/canvas/
├── models.py        # CanvasSession / CanvasPage / CanvasStroke
├── services.py      # CanvasSessionService (locking/fencing)
│                    # CanvasSyncService (pages/strokes/finalize)
├── serializers.py   # incl. StrokeBatchSerializer, Heartbeat/Takeover
├── views.py         # thin ViewSets + @action heartbeat/takeover/strokes/finalize
├── urls.py          # router: canvas/sessions, canvas/pages
└── migrations/      # 0001_initial, 0002_enable_rls
```

## Frontend structure additions (Phase 2)

```text
src/features/canvas/
├── canvasStore.ts    # session/pages/generation/lockLost state (zustand)
└── CanvasEditor.tsx  # drawing surface, timers (heartbeat/flush), takeover UX

src/services/api/canvas.ts     # typed canvas endpoints
src/services/sync/outbox.ts    # transport: grouped flush + lock-lost signal
```

## Request/data flow for a stroke (end to end)

```text
pointerup → build stroke {uuid, sequence_order, points, idempotency_key}
  → IndexedDB putStroke (immediate, §4)
  → outbox queueOperation (pending)
  → flush loop (3 s / per-stroke / visibility / unload)
  → grouped POST /canvas/pages/{id}/strokes {device_id, lock_generation, strokes[]}
  → server: lock session row → ensure_lock → savepoint-create each stroke
  → duplicates reported; ops acknowledged client-side
```

## Invariants honored (cumulative)

All Phase 1 invariants hold unchanged. New:

| Invariant | How it holds |
|---|---|
| Canvas synchronization uses an outbox (§32 #16) | IndexedDB outbox is the only write path from the editor |
| Canvas ownership uses fencing tokens (§32 #18) | generation checked on every mutating call; takeover increments |
| Historical data preserved / no arrays duplicating relations | strokes relate by page_id + sequence_order |

## Component inventory status

| Area | Status |
|---|---|
| Auth/accounts/profiles/subjects | ✅ |
| Canvas backend + frontend | ✅ (finalize ⚠️ awaits Phase 3 extension) |
| Offline sync | ✅ core (failure-state persistence 🟡) |
| Jobs runtime | 🔧 model only |
| Providers/storage serving | ⚠️/🔧 |
| Ingestion → AI Classroom pipeline | ❌ |
| Ops hardening (rate limits, metrics, backups, CI, deploy) | ❌ |
