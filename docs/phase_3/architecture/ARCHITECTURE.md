# Architecture — after Phase 3

Repository state following Phases 1–3. Phase 1/2 structure documented in [`../phase_2/architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) remains valid; this page adds the ingestion layer.

## Product modules status

| Module / Layer | Status |
|---|---|
| Security foundation (auth, profiles, subjects, RLS, error contract) | ✅ |
| Canvas + offline sync (input capture) | ✅ |
| Shared ingestion (canonical documents, OCR jobs, storage) | ✅ (OCR providers 🔧 mock) |
| NoteSpace renderer/PDF | ❌ Phase 4 |
| AI Classroom (chunk→retrieve→enrich→learn) | ❌ Phases 5–7 |

## New backend components (Phase 3)

```text
apps/documents/
├── models.py         # Document · DocumentPage · DocumentPageRevision · DocumentLine
├── services.py       # IngestionService (create/finalize/edit) · run_ocr_job (§47)
├── serializers.py · views.py (DocumentViewSet + FinalizeUploadView + JobViewSet
│                     + CancelJobView) · urls.py
├── migrations/       # 0001_initial · 0002_enable_rls

apps/jobs/
├── services.py       # get_or_create_job · dispatch_job · execute/run_claimed_job
│                     # promote_due_retries · reap_stuck_jobs · cancel_job
├── tasks.py          # Celery task definitions
└── management/commands/process_jobs.py   # DB-polling executor (§24)

providers/
├── ocr/{mock,chain}.py   # mock providers + primary→fallback chain (§28)
└── storage/{local,views}.py  # byte ops + signed upload/download serving
```

## End-to-end data flow (implemented)

```text
Photo upload ────────────┐
                         ▼
              signed PUT → object storage
                         ▼
        finalize-upload: sha256 → DocumentPageRevision
                         ▼
        logical OCR job (idempotency key §20) ──► dispatch (eager/broker)
                         ▼
        claim → RLS context → primary→fallback OCR
                         ▼
        DocumentLines + snapshot + status (completed | needs_review)

Canvas page finalize ───► rasterize PNG → same pipeline (one transaction, §67)
```

## Invariants honored (new this phase)

| Invariant | How it holds |
|---|---|
| Every async job idempotent (§32 #10) | unique keys at creation + claim + completed short-circuit |
| AI failure ≠ source failure (§28) | OCR failure touches jobs/status only; documents/images intact |
| Canonical revisions immutable (§7) | edits create revisions; no mutation path exists |
| Provider SDKs isolated (§24) | chain/mock behind `OCRProvider`; apps import interfaces |
| Workers establish trusted RLS context (§47/§79 #16) | executor wraps handlers; profile comes from job payload |

## Component inventory status

| Area | Status |
|---|---|
| Auth/profiles/subjects/canvas/offline sync | ✅ |
| Ingestion + storage + job runtime | ✅ (providers 🔧, reaper scheduling ⚠️, storage 🟡 local) |
| Jobs API (get/cancel) | ✅ |
| NoteSpace PDF / AI Classroom | ❌ |
| Ops hardening | ❌ |
