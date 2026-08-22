# Assumptions and Decisions — Phase 6

Prior decisions remain in force (A/B/C/D/E-series in [`../phase_5/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../architecture/ASSUMPTIONS_AND_DECISIONS.md)). Phase 6 decisions (F-series):

| ID | Decision |
|---|---|
| F-001 | Embeddings: local feature-hashing provider (384-d, L2-normalized uni+bigrams) until a neural local model is adopted. |
| F-002 | LLM text generation via **MockLLMProvider** — deterministic restructuring of supplied evidence only; cannot invent uncited content. |
| F-003 | Pipeline orchestration = explicit sequential stage functions with jsonschema validation; **no LangGraph dependency** for v1. |
| F-004 | `POST /api/v1/search` added beyond the §60 blueprint to exercise retrieval (also consumed by enrichment). |
| F-005 | Evidence verifier = rules-v1 lexical support ratio against cited chunk contents; thresholds 0.60/0.30 settings-driven; uncalibrated pending labeled data. |
| F-006 | Enrichment identity = sha256 over {document, current revision ids, prompt versions, model}; active-note unique constraint `(document, content_hash) WHERE NOT superseded`. |
| F-007 | refresh-ai supersedes the active note and always enqueues; superseded notes retained (§27). |
| F-008 | Evidence payload passed to the mock as JSON appended after an `EVIDENCE_JSON:` sentinel in the prompt user-text — the seam a real provider will reuse. |

---

## Details

### F-002 — Mock LLM that cannot hallucinate
- **Why:** §51 forbids silently presenting general knowledge as user content; §72 treats evidence as data. A mock that only restructures the supplied evidence makes those guarantees *structural* rather than behavioral.
- **Consequences:** enrichment text is synthetic but grounded; every block cites exactly the chunks it derived from.
- **Swap path:** real provider implements the same protocol + schemas; grounding checks then become behavioral (verifier + eval harness already exist).

### F-003 — No LangGraph dependency
- **Why:** graph semantics needed today are linear with per-node schema validation; adding langgraph/langchain-core before any real model exists buys nothing.
- **Alternatives:** langgraph StateGraph now.
- **Migration path:** stages are isolated functions with typed inputs/outputs — wrapping them in a graph runner later is mechanical.

### F-005 — Rules-based verifier
- **Why:** deterministic, testable, and honest about what similarity can prove (§12: candidate signal, not proof).
- **Semantics:** support ratio = |tokens(block) ∩ tokens(cited)| / |tokens(block)|, best across citations. supported ≥ 0.60 · partially ≥ 0.30 · else unsupported · no refs → not_verified.
- **Consequences:** meta-text blocks (overview) legitimately score unsupported — surfaced honestly to users rather than hidden.

### F-006/F-007 — Identity & retention
- Active-note partial unique constraint allows superseded history rows with identical hashes.
- Refresh never deletes: old generations remain queryable/auditable.

### Deferred
Verifier calibration dataset + labeling process; coalescing window and quota budgets; question-generation prompts (Phase 7); chat prompt (Phase 7).
