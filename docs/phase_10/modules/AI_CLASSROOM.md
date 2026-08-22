# AI Classroom Module — Phase 10

**Status:** Extended with tag rename endpoint, enrichment coalescing, budget integration

---

## Phase 10 Changes

### Tag Rename Endpoint (B4)
- **New Endpoint**: `POST /api/v1/tags/{id}/rename/`
- **Body**: `{ "name": "New Display Name" }`
- **Behavior**: Updates `Tag.display_name` only; `stable_key` unchanged
- **Audit**: Creates `TagChangeLog` entry with `change_type=RENAMED`
- **Auth**: Owner-scoped via subject → profile → user

### Enrichment Coalescing (B7)
- **Coalesce Window**: `ENRICHMENT_COALESCE_WINDOW_SECONDS` (default 300s)
- **Change-Magnitude Threshold**: `ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD` (default 0.15)
- **Logic**: Within window, check for pending enrichment job on same document; if change magnitude ≤ threshold, reuse existing job
- **Traceability**: Added `coalesced_from` FK on `Job` model linking to previous job

### Monthly Budget Integration (B8)
- **AIBudgetThrottle**: Applied to `DocumentViewSet.enrich`, `refresh_ai`, `ChatSessionViewSet.messages`
- **BudgetService**: Per-profile monthly token/cost limits with automatic reset
- **ProviderCallLog**: Token fields populated (`input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`)

---

## Existing Capabilities (Preserved)

- **Enrichment Pipeline**: 6-stage (Retrieve → Draft → Gap Detection → Gap Filling → Citation Stitching → Evidence Verification)
- **Schema Validation**: JSON Schema validation at each LLM stage
- **Evidence Verifier**: Rule-based lexical support with `SUPPORTED`/`PARTIALLY_SUPPORTED`/`UNSUPPORTED`
- **Stable Tags**: `Tag` identity = (subject, stable_key); display names renameable
- **Revision-Aware Questions**: Bind to exact source revision/chunk
- **Adaptive Tests**: EMA mastery tracking, atomic attempt grading

---

## API Endpoints (Phase 10 Additions)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tags/{id}/rename/` | Rename tag display name |
| GET | `/api/v1/documents/{id}/questions` | List questions for document |

---

## Models Updated

- **Job**: Added `coalesced_from` FK for enrichment coalescing traceability
- **UserProfile**: Added `monthly_token_budget`, `monthly_cost_budget_usd`, `current_month_token_usage`, `current_month_cost_usd`, `budget_reset_date`
- **ProviderCallLog**: Token fields (`input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`) now populated

---

## Security Enhancements (Global, D4/D5)

- **Prompt-Injection Directive**: Prepended to all LLM system prompts
- **Data-Minimization Filter**: Truncation + PII redaction (email, phone, credit card, SSN) with `redactions_count` logged
- **Applied To**: All LLM calls via `LLMChainProvider.generate_structured()`

---

## Tests Added

- `apps/ai_classroom/tests/test_tag_rename.py` — 6 tests (rename, empty, too long, same name, other user, not found)
- Existing enrichment flow tests: 9 tests passing

---

## Configuration

```bash
# Enrichment coalescing
ENRICHMENT_COALESCE_WINDOW_SECONDS=300
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15

# Budget defaults
DEFAULT_MONTHLY_TOKEN_BUDGET=100000
DEFAULT_MONTHLY_COST_BUDGET_USD=50.00

# Provider input limits
MAX_PROVIDER_INPUT_CHARS=8000
```

---

## Related Documentation

- `docs/phase_6/ai/AI_PIPELINE.md` — Full pipeline specification
- `docs/phase_6/ai/AI_EVALUATION.md` — Evaluation harness
- `docs/phase_6/ai/RAG_AND_RETRIEVAL.md` — Retrieval architecture