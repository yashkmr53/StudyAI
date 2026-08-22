# AI Pipeline

## Status: ❌ No AI pipeline exists

No OCR, embedding, LLM, or orchestration code is implemented. No provider credentials are configured. The only implemented artifacts are the **interfaces** and **idempotency key formats** below.

## Implemented pieces

| Piece | Location | Content |
|---|---|---|
| Provider protocols | `providers/base.py` | `OCRProvider.recognize`, `LLMProvider.generate_structured(prompt, schema)`, `EmbeddingProvider.embed(texts, model_version)`, `ObjectStorageProvider` (upload/download/delete URLs) |
| Result types | `providers/base.py` | `OCRResult{lines, confidence, provider, raw_ref}`, `Prompt{name, version, system, user}`, `StructuredLLMResult{data, model, prompt_name, prompt_version}` |
| Registry | `providers/registry.py` | 🔧 getters raise `NotImplementedError` — explicit stubs |
| Key formats | `shared/idempotency/keys.py` | `ocr:…`, `embedding:…`, `enrichment:…`, `question_generation:…` |

## Pipeline stages (all ❌)

```text
OCR → normalization → chunking → embedding → retrieval → reranking
    → LLM calls (draft/gap/cite/verify) → enrichment persistence
    → tags → questions → tests → chat → revision planning
```

Orchestration: spec names LangGraph for enrichment; no workflow library is installed.

## Model/provider inventory

| Stage | Provider | Model | Version | Input | Output | Prompt location | Schema | Fallback | Retry | Timeout | Cost tracking | Evaluation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OCR | *unselected* (spec §30 open) | — | — | — | — | — | — | — | — | — | — | — |
| Embeddings | local model planned | — | — | — | — | n/a | — | — | — | — | — | — |
| Enrichment/Chat/Questions LLM | *unselected* | — | — | — | — | — | — | — | — | — | — | — |
| Reranker | none planned for v1 unless measured need | — | — | — | — | — | — | — | — | — | — | — |

Every column is intentionally empty: recording placeholders would imply decisions that haven't been made.

## Contracts every future stage must satisfy

1. Structured, schema-validated outputs from Draft onward.
2. Versioned prompts (`name:version`) and recorded model/provider/config per generation.
3. Idempotent execution keyed per §20 formats.
4. Data minimization before external calls (§73); retrieved content treated as untrusted data (§72).
5. Failure isolation: provider failure never touches source data (§28).
