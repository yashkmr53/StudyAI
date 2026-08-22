# NoteSpace (Module 1)

## Implementation status: ❌ Renderer/PDF not implemented — ingestion input layer now exists

What changed in Phase 3, relevant to NoteSpace:

- Finalized canvas pages and uploaded photos now flow into **canonical documents** (`apps/documents/models.py`) with immutable revisions and per-revision lines — exactly the input NoteSpace will render from (§49).
- OCR output currently comes from 🔧 mock providers; transcription text is synthetic until a real provider lands (§30).

Still missing for NoteSpace itself: layout-aware renderer, PDF generation, immutable DigitizedDocument artifacts, secure PDF download endpoints. The module contract (does / does-not-do / semantic-modification prevention) remains as specified in [`../phase_1/modules/NOTE_SPACE.md`](../../phase_1/modules/NOTE_SPACE.md).

Note: the Phase 3 rasterizer (`apps/canvas/raster.py`) is ingestion plumbing only — it is explicitly *not* the faithful NoteSpace renderer.
