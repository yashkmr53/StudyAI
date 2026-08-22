# Implementation Status — Phase 4

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~37% of full v4.1 scope (Phases 1–4 of 8 complete)
Completed:          Security foundation; canvas/offline; shared ingestion;
                    NoteSpace end-to-end — faithful renderer, PDF generation,
                    immutable content-addressed artifacts, async render jobs,
                    authz-gated signed downloads, full frontend module UI
Partial:            RLS enforcement (dev superuser bypass), reaper scheduling,
                    object storage serving (local variant)
Mocked/stubbed:     OCR providers (mock), password-reset email,
                    LLM/embedding registries
Unimplemented:      AI Classroom entirely (chunking/embeddings/retrieval/
                    enrichment/tags/mastery/questions/tests/chat/revision),
                    reference books, evaluation harness, rate limiting,
                    audit logging, metrics/health endpoints, backups, CI,
                    deployment artifacts
Major risks:        Synthetic OCR text (mock); no backups; no CI;
                    single-machine storage; RLS unenforced for dev superuser
```

## Phase 4 feature audit

### NoteSpace backend

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Layout-aware renderer | §7, §49 | ✅ | `apps/documents/pdf_renderer.py` (fpdf2 + vendored DejaVu) | `tests/api/test_note_space.py::LayoutExtractionPurityTests` | Lines emitted verbatim in source order; headings styled only when `is_heading` explicitly flagged; page numbers + document metadata as §49 furniture | No images-in-PDF yet (source has none) |
| Faithfulness guarantee | §7 "never summarizes/corrects" | ✅ | renderer consumes line texts only — no code path can add content; extraction purity test asserts verbatim mapping | purity test | By-construction boundary | Human visual QA pending real OCR text |
| Unicode rendering | implied by faithfulness | ✅ | vendored DejaVu Sans (+Bold), license-permitted redistribution | PDF magic/size tests | Core fonts rejected non-latin-1 → would violate faithfulness | CJK coverage: DejaVu lacks CJK glyphs (see limitations) |
| PDF generation perf | §75 <10 s target | ✅ | fpdf2 render of small docs is ms-scale (15 KB artifact in E2E) | E2E smoke | Formal perf test not written | — |
| DigitizedDocument model | §7 | ✅ | `documents/models.py` | artifact suites | content-addressed: unique(document, hash incl. revisions+renderer_version); revision_ids JSON recorded | Spec's singular revision_id generalized to per-page list (D-002) |
| Immutability + retention | §7/§27/§69 | ✅ | new hash ⇒ NEW artifact; old artifacts never deleted or overwritten | regen tests assert old retained | — | Storage GC for superseded artifacts not built |
| Async render job | §22/§60/§19 | ✅ | job_type `pdf_render`; eager/broker dispatch; idempotency key `pdf:{doc}:{hash32}` | request-pdf suite | Duplicate request returns existing artifact (200) instead of re-rendering | — |
| POST /documents/{id}/pdf | §60 | ✅ | `DocumentViewSet.request_pdf` | api tests | 200 existing / 202 enqueued | — |
| GET /digitized-documents[?document=] · /{id} | §60 | ✅ | list+retrieve ViewSet, owner-scoped | api tests | `document` filter added beyond blueprint for UI convenience | — |
| GET …/download → signed URL | §60/§23/§49 | ✅ | ownership check → short-lived HMAC URL JSON `{url, expires_in}`; object-existence check | secure-access tests | JSON-with-URL chosen over 302 so the browser fetch needs no auth header (D-004) | — |
| RLS on digitized documents | §3 | ⚠️ | migration `documents/0004_enable_rls_digitized.py` EXISTS chain | policy present via pg_policies | Same superuser caveat as all phases | Restricted-role behavioral test pending |

### NoteSpace frontend

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Upload flow UI | §45–46 | ✅ | `features/notespace/NotespacePage.tsx` — file input → create → PUT signed → finalize | manual E2E | Shows live ocr_status chips | — |
| Document list/detail | §63 | ✅ | same file | manual E2E | Pages grouped w/ status chips, confidence %, headings bold | — |
| Transcription editor | §48 | ✅ | inline per-line edit + heading checkbox → submitEdit creates immutable revision | manual E2E | Page-level reload after save (v1 simplicity) | No diff view vs old revision |
| Generate/download PDF UI | §49/§60 | ✅ | request → poll digitized-documents → download via signed URL (new tab) | manual E2E | — | — |

## Carried over

All Phase 1–3 audits remain valid ([`../phase_3/IMPLEMENTATION_STATUS.md`](../phase_3/IMPLEMENTATION_STATUS.md)): auth, profiles/subjects, canvas/offline, ingestion pipeline, job runtime, jobs API. OCR providers remain 🔧 mocks.

## Final implementation audit

```text
Total architecture requirements tracked: 78   (was 71 after Phase 3)
Fully implemented:            42
Partially implemented:         3
Simplified/alternative:        5
Mocked/stubbed:                3
Not implemented:              25

Tests passing:   backend 67/67 (PostgreSQL); 65 pass + 2 skip (SQLite)
                 frontend 1/1 vitest; production build green
Tests failing:   0
Tests skipped:   2 (PostgreSQL-only RLS tests under SQLite settings)
Coverage:        not measured
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          tokens in localStorage; password reset stub
Known operational issues: no backups, no health endpoints, no CI, reaper
                          unscheduled, local-FS storage only
Known AI-quality issues:  OCR output synthetic (mock); review threshold
                          uncalibrated; DejaVu has no CJK glyph coverage
Known architectural deviations: DigitizedDocument.revision_id generalized to a
                          per-page revision list (D-002); download endpoint
                          returns a signed-URL payload rather than a redirect
                          (D-004); local-FS storage (C-002)
```
