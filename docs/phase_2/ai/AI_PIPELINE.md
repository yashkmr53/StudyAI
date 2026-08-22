# AI Pipeline

## Status: ❌ No AI pipeline exists (unchanged after Phase 2)

No OCR, embedding, LLM, or orchestration code. Only interfaces (`providers/base.py`), explicit registry stubs, and idempotency key formats exist.

Full stage-by-stage inventory and the empty provider/model table: [`../phase_1/ai/AI_PIPELINE.md`](../../phase_1/ai/AI_PIPELINE.md).

Phase 2 addition relevant to the pipeline: the finalize flow is the designated producer of the first OCR job; its transaction contains the marked extension point (`CanvasSyncService.finalize_page`).
