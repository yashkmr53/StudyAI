# NoteSpace (Module 1)

## Implementation status: ✅ Implemented end-to-end (with mock-OCR caveat)

Phase 4 completes Module 1: canonical revisions → faithful typed PDF → secure download, plus the user-facing module at `/notespace`.

## Actual flow

```text
Input: uploaded photo OR finalized canvas page
 ↓
OCR (🔧 mock provider) → DocumentLines on an immutable revision
 ↓
(optional) User edits transcription → NEW revision; old preserved
 ↓
Layout-aware renderer — verbatim lines, explicit-flag headings only
 ↓
PDF (fpdf2 + DejaVu, page numbers + metadata)
 ↓
DigitizedDocument (content-addressed, immutable)
 ↓
Private storage → authorization-gated short-lived signed download
```

## What NoteSpace does

- Faithful transcription rendering; typesetting normalization only.
- Headings styled only when explicitly flagged in the source (`is_heading`).
- Page numbering and document metadata (§49 allowance).
- Regeneration-safe: unchanged content returns the same artifact; edits produce new artifacts while old ones remain.

## What NoteSpace does NOT do

- No summarizing/paraphrasing/semantic correction/inference/explanations — enforced by construction: the renderer's only input is line texts.
- No dependency on AI Classroom availability or success.

## Status detail

| Piece | Status |
|---|---|
| Models/API/frontend | ✅ |
| Transcription source | 🔧 mock OCR (§30 decision open) |
| Images inside PDFs | ❌ not yet represented in sources |
