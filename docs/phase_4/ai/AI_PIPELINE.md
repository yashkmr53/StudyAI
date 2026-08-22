# AI Pipeline

## Status after Phase 4

Unchanged from Phase 3: the OCR stage executes end-to-end on 🔧 mock providers; everything downstream remains ❌. See [`../phase_3/ai/AI_PIPELINE.md`](../ai/AI_PIPELINE.md).

New Phase 4 precedent relevant to future LLM stages: `pdf_render` demonstrates a second job type flowing through the same durable state machine, plus renderer-version metadata stored per artifact (`RENDERER_VERSION`) — the same versioning discipline §13 requires for prompts/models.
