# AI Pipeline

## Status after Phase 3

The OCR stage of the pipeline now **executes end-to-end** — but on 🔧 mock providers. Everything downstream (chunking → embeddings → retrieval → LLM stages) remains ❌.

## What actually runs today

| Stage | Component | Status | Notes |
|---|---|---|---|
| Ingest trigger | finalize-upload / canvas finalize | ✅ | creates logical OCR job |
| Logical job + idempotency | `get_or_create_job` + §20 key | ✅ | duplicates return existing job |
| Claim + RLS context | `run_claimed_job` | ✅ | trusted profile from job payload (§47) |
| Primary OCR attempt | `OCRChainProvider` slot 1 | 🔧 mock (`mock` / `mock_low_confidence`) | deterministic fake lines |
| Fallback attempt | chain slot 2 | ✅ mechanism / 🔧 provider | attempts recorded in snapshot |
| Normalization | existence + readability checks only | 🟡 | no image enhancement |
| Line persistence | atomic DELETE+INSERT per revision | ✅ | safe re-runs |
| Review classification | avg confidence < 0.80 → needs_review | ✅ rule / ⚠️ threshold uncalibrated | C-009 |
| Downstream enqueue | extension point in `run_ocr_job` | ❌ | Phase 5 chunking |

Provider/model inventory is otherwise unchanged from [`../phase_1/ai/AI_PIPELINE.md`](../../phase_1/ai/AI_PIPELINE.md): no LLM, embedding, or reranker exists; §30 provider decision still open.

Per-generation metadata now recorded in practice for OCR: provider name + attempted chain stored in `DocumentPageRevision.ocr_provider` / `content_snapshot`.
