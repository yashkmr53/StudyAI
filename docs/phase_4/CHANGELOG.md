# Changelog

## [0.5.0] — 2026-08-22 — Phase 4: NoteSpace

| Field | Detail |
|---|---|
| Change | Implemented Phase 4 of the v4.1 order (§31 items 25–28): layout-aware PDF renderer, async render jobs, immutable content-addressed DigitizedDocument artifacts, authorization-gated signed downloads, and the NoteSpace frontend module |
| Reason | Module 1 of the product; completes canonical→product pipeline for typed notes |
| Files/modules affected | `backend/apps/documents/{models,pdf_renderer,note_space,services,serializers,views}.py`, `backend/apps/documents/migrations/000[3-4]*`, `backend/apps/jobs/services.py`, `backend/config/settings/base.py`, `backend/assets/fonts/*` (vendored DejaVu), `backend/tests/api/test_note_space.py`, `frontend/src/features/notespace/NotespacePage.tsx`, `frontend/src/services/api/documents.ts`, `frontend/src/routes/index.tsx`, `backend/requirements.txt`, `docs/phase_4/**` |
| Database migration | documents 0003 (is_heading + DigitizedDocument) · documents 0004 (RLS on digitizeddocument) |
| API impact | Added `POST /documents/{id}/pdf` (200 existing / 202 job), `GET /digitized-documents[?document=]`, `GET /digitized-documents/{id}`, `GET /digitized-documents/{id}/download`; revisions responses now embed `lines` |
| Breaking changes | none |

### Backend

- Faithful renderer: fpdf2 + vendored DejaVu Sans/Bold (Unicode-safe; core fonts rejected non-latin-1). Verbatim line output, explicit-flag headings only, footer page numbers + document metadata per §49.
- DigitizedDocument: content-addressed identity (sha256 over descriptor incl. renderer_version + per-page revisions/hashes/lines); unique(document, hash); superseded artifacts retained.
- pdf_render job type through the shared runtime: claim → RLS context → double-checked render → storage → artifact row; idempotency key `pdf:{doc}:{hash32}`; duplicate requests return existing artifact.
- Download endpoint: ownership check → object existence → short-lived HMAC signed URL payload.
- RLS policy on the new table.

### Frontend

- NotespacePage: upload card (create → PUT signed URL → finalize), documents list, detail view with per-page OCR status chips and confidence percentages, inline transcription editor with heading flags, Generate-PDF button polling to completion, download via signed URL.

### Verification

Backend: 67 tests green on PostgreSQL (65 pass + 2 RLS skips on SQLite). Manual E2E: upload → OCR → heading edit → revision 2 → PDF generated (~15 KB) → signed download returned `%PDF-1.3`; intruder account blocked (404). Frontend build + vitest green.

## [0.4.0] — Phase 3 · [0.3.0] — Phase 2 · [0.2.0] — Docs restructure · [0.1.0] — Phase 1
See prior phase CHANGELOGs: [`../phase_3/CHANGELOG.md`](../phase_3/CHANGELOG.md) and earlier.
