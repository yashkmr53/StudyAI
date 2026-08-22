# Architecture — after Phase 4

Delta documentation: Phases 1–3 architecture remains as documented in [`../phase_3/architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md).

## Module status board

| Module / Layer | Status |
|---|---|
| Security foundation | ✅ |
| Canvas + offline sync | ✅ |
| Shared ingestion | ✅ (OCR 🔧 mock) |
| **NoteSpace (Module 1)** | ✅ end-to-end ([modules/NOTE_SPACE.md](../modules/NOTE_SPACE.md)) |
| AI Classroom (Module 2) | ❌ Phases 5–7 |
| Ops hardening | ❌ Phase 8 |

## New backend components (Phase 4)

```text
apps/documents/
├── pdf_renderer.py    # fpdf2 + vendored DejaVu; verbatim rendering contract
├── note_space.py      # NoteSpaceService: layout extraction, descriptor hashing,
│                      # request_pdf, render_and_store, signed download URLs
└── migrations/000[3-4]*
apps/jobs/services.py  # + pdf_render handler registration
assets/fonts/          # DejaVuSans.ttf, DejaVuSans-Bold.ttf (vendored)
```

## New frontend components

```text
src/features/notespace/NotespacePage.tsx   # upload → OCR review/edit → PDF
src/services/api/documents.ts              # typed client for documents/digitized
```

## End-to-end product flow now working

```text
Upload photo ──► OCR(🔧mock) ──► lines on immutable revision
                                     │ user edits (new revision)
                                     ▼
                    POST /pdf → render job → PDF in private storage
                                     │
                    authz check → signed URL → download
```

## Invariants honored (new this phase)

| Invariant | How it holds |
|---|---|
| NoteSpace never performs semantic interpretation (§32 #3) | renderer consumes verbatim line texts only; purity test |
| Generated artifacts reference exact source revisions (§32 #7) | revision_ids + content hashes inside artifact identity |
| Immutable artifacts (§27) | unique(document,hash); superseded artifacts retained |
| Renderer versioning recorded (§13-adjacent) | RENDERER_VERSION stored and identity-relevant |

## Component inventory status

| Area | Status |
|---|---|
| Foundation + canvas + ingestion | ✅ |
| NoteSpace module (backend + frontend) | ✅ |
| Job runtime | ✅ (2 job types live) |
| AI Classroom / retrieval / evaluation | ❌ |
| Ops hardening | ❌ |
