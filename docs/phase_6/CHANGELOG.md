# Changelog

## [0.7.0] — 2026-08-22 — Phase 6: AI Classroom Intelligence

| Field | Detail |
|---|---|
| Change | Implemented Phase 6 of the v4.1 order (§31 items 36–42): generated-layer models, prompt registry, schema-validated enrichment pipeline A–F, rules-based evidence verifier, enrich/enrichment/refresh-ai endpoints, ai_stale propagation, evaluation harness + command |
| Reason | Next phase of the implementation order; delivers Module 2's core intelligence machinery |
| Files/modules affected | `backend/apps/ai_classroom/**` (models/prompts/schemas-via-jsonschema/services/views_serializers/migrations), `backend/apps/evaluation/**` (new: models/runner/command), `backend/providers/llm/mock.py`, `backend/apps/retrieval/services.py` (ai_stale hook), `backend/apps/documents/views.py` (enrichment actions), `backend/config/settings/base.py`, `backend/tests/api/test_ai_classroom.py`, `docs/phase_6/**` |
| Database migration | ai_classroom 0001_initial · 0002_enable_rls · evaluation 0001_initial |
| API impact | Added `POST /documents/{id}/enrich`, `GET /documents/{id}/enrichment`, `POST /documents/{id}/refresh-ai`; new job type `enrich` visible via /jobs |
| Breaking changes | none |

### Backend — generated layer

- EnrichedNote with active-note partial unique constraint `(document, content_hash) WHERE NOT superseded`; supersede-and-retain regeneration semantics; ai_stale flag propagated automatically when indexing detects content changes.
- EnrichedNoteBlock with generation_method dimension; CitationBlock with §12 source_refs shape and independent verification_status/score/verifier_version.
- PromptVersion registry seeded with v1 templates for enrichment_draft/gap_detection/gap_filling.

### Backend — pipeline

- Stages A retrieve → B draft → C gap detection → D gap filling → E citation stitching → F evidence verification, each LLM stage validated against a jsonschema schema after generation.
- MockLLMProvider: deterministic evidence restructuring only — structurally incapable of uncited invention.
- EvidenceVerifier rules-v1: lexical support ratio vs cited chunk contents; supported ≥0.60 / partially ≥0.30 / unsupported; not_verified without refs. E2E demonstrated discriminating verdicts (overview unsupported 0.0; key_concept supported 1.0; reference-grounded gap_fill supported 0.83).
- Failure isolation: job-level retryable/dead-letter only; canonical data untouched.

### Backend — evaluation

- EvalRun model; retrieval runner (Recall@k/MRR/Precision@k) and citation runner (support precision/recall); `run_ai_evaluation` command. Dataset itself remains empty (§26 golden-set work pending).

### Verification

Backend suite: 89 tests — green on PostgreSQL (89/89) and SQLite (86 pass + 3 skips). Manual E2E against PostgreSQL incl. reference-grounded gap fill from a READY book and refresh-ai creating a retained second generation. Frontend build + vitest green.

## [0.6.0] — Phase 5 · earlier
See [`../phase_5/CHANGELOG.md`](../phase_5/CHANGELOG.md).
