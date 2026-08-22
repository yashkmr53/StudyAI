# NoteSpace (Module 1)

## Implementation status: ❌ Not implemented

No NoteSpace code exists beyond an empty Django app skeleton (`backend/apps/notespace/`) and a placeholder frontend route. This document records the module contract it must satisfy when built (Phase 4), so the boundary is explicit from day one.

## Planned flow

```text
Input (photo upload or finalized canvas page)
 ↓
OCR → canonical DocumentPageRevision (+DocumentLine*)
 ↓
Layout extraction (text + line geometry)
 ↓
Typesetting rules
 ↓
PDF renderer
 ↓
DigitizedDocument (immutable, tied to revision_id)
 ↓
Private object storage → short-lived signed download URL
```

## What NoteSpace does

- Faithful transcription and typesetting of the user's captured content.
- Presentation normalization only: layout, fonts, page numbering, document metadata.
- Headings included **only** where the source explicitly represents them; images only where retained.

## What NoteSpace does NOT do

- No summarizing, paraphrasing, or semantic correction.
- No inferring missing information.
- No explanations or added AI knowledge.
- No coupling to AI Classroom availability — a failed AI job never hides or blocks the PDF.

## How semantic modification is prevented (design)

1. The renderer's only input is `DocumentLine` rows (text + bbox + confidence) from a specific immutable revision — there is no pathway for LLM output to enter rendering.
2. Generated artifacts (`DigitizedDocument`) are separate entities referencing `revision_id`; they never mutate source revisions.
3. Module boundary enforced by code organization: `apps/notespace/` must not import from `ai_classroom`/LLM providers. (Not yet enforceable in review since neither exists.)

## API surface (planned, spec §60)

```text
POST /api/v1/documents/{id}/pdf               → 202 + job resource
GET  /api/v1/digitized-documents/{id}
GET  /api/v1/digitized-documents/{id}/download → signed URL after authorization
```
