# Assumptions and Decisions — Phase 3

Prior decisions remain in force: A-001…A-020 ([`../phase_1/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../../phase_1/architecture/ASSUMPTIONS_AND_DECISIONS.md)), B-001…B-012 ([`../phase_2/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../architecture/ASSUMPTIONS_AND_DECISIONS.md)). This page records Phase 3 decisions (C-series).

| ID | Decision |
|---|---|
| C-001 | OCR runs on **mock providers** (`mock`, `mock_low_confidence`, `failing`) until the §30 provider decision is made; the chain mechanism is production-shaped. |
| C-002 | Local-FS storage serving views stand in for direct-to-S3 uploads; signed tokens are the authorization. |
| C-003 | Job execution defaults to Celery **eager mode in dev/test** (inline, no Redis); `manage.py process_jobs` is the broker-free DB-polling executor (§24 alternative); production uses real workers. |
| C-004 | Retry policy: max 3 attempts, exponential backoff 5s·2^n capped at 300s + jitter via `next_retry_at`. |
| C-005 | Canvas pages are rasterized to PNG by a pure-stdlib minimal renderer so finalize can feed ingestion (§67). This is *not* the NoteSpace PDF renderer. |
| C-006 | `DocumentPage.current_revision_id` and `Job.profile_id` are plain UUID columns (no FK) to avoid circular FKs / premature cascade semantics; consistency is enforced in services. |
| C-007 | `reference_book_id` stored as nullable UUID on Document until the references model exists (Phase 5). |
| C-008 | OCR idempotency: duplicate finalize of identical content returns the existing job rather than creating a new one (unique key §20). Failed/dead jobs for identical content are requeued, not duplicated. |
| C-009 | Review threshold hardcoded at 0.80 avg confidence → `needs_review`; calibration deferred to evaluation phase (§26). |
| C-010 | Upload keys are namespaced `{profile_id}/{page_id}{ext}` — enables ownership checks on signing and keeps objects page-scoped. |
| C-011 | `DATA_UPLOAD_MAX_MEMORY_SIZE` set above `UPLOAD_MAX_BYTES` so oversize uploads receive a clean 413 envelope from our view. |
| C-012 | User-edit revisions (§48) accept a lines array; server recomputes content hash from canonical JSON and persists lines immediately with `edited_by` attribution. |

---

## Details

### C-001 — Mocked OCR, real machinery
- **Context:** spec §30 explicitly leaves the handwriting provider open; no API keys exist.
- **Decision:** deterministic mock providers exercise every non-provider concern: job claiming, fallback attempts, review thresholds, line persistence, RLS-scoped execution.
- **Consequences:** recognized text is synthetic; docs must never imply real transcription. Swapping in a real provider = implement protocol + register in `_build_ocr` + change settings.
- **Architecture impact:** none — interface-first per §24.

### C-003 — Three execution modes
- **Why:** dev machines lack Redis; tests need determinism; production needs durability.
- **Mechanics:** eager inline → same handler path as broker mode; DB-polling executor proves §24's stated alternative while sharing the entire state machine.
- **Consequences:** in eager mode jobs complete before the HTTP response returns; responses are refreshed post-dispatch so clients see terminal state.

### C-005 — Minimal rasterizer
- **Why:** §6's input is "Photo / Finalized Canvas Page"; without an image there is nothing to OCR.
- **Alternatives:** headless browser rendering (heavy), Pillow (new dep), deferring canvas→ingestion entirely (breaks §67).
- **Consequences:** low-fidelity bitmap — acceptable because mock OCR ignores pixels anyway; replaced wholesale if a richer export is needed. Clearly distinct from NoteSpace's faithful renderer (§49).

### C-008 — Idempotent requeue semantics
- **Why:** retry-processing must not multiply jobs for unchanged content.
- **Rule:** same content-hash ⇒ same key ⇒ existing job; only failed states get reset to QUEUED.

### Deferred (unchanged from spec §30)
Real OCR provider(s) and fallback ordering; hosting; retention of raw OCR responses (mock results currently retained inside snapshots); manual-OCR-edit UX polish.
