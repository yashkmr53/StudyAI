# Known Limitations — after Phase 6

Carried over: [`../phase_5/KNOWN_LIMITATIONS.md`](../phase_5/KNOWN_LIMITATIONS.md) (RLS superuser bypass, rate limiting, password-reset stub, localStorage tokens, outbox failure states/debounce, stroke metadata, concurrency/editor tests, multi-tab UX, OpenAPI warnings, coverage unmeasured, no CI/deploy artifacts/health endpoints/audit logging/backups, mocked OCR + synthetic transcription, image normalization absent, storage GC, magic-byte sniffing, hashing-embedding lexical grade + CJK gaps).

## New or changed in Phase 6

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | LLM text generation | 🔧 MockLLMProvider restructures supplied evidence only | §11 LLM-drafted enrichment with real reasoning | No natural-language synthesis; blocks echo evidence | Enrichment reads as extractive summaries | Select real model (§30); implement provider; grounding becomes behavioral |
| 2 | Verifier calibration | ⚠️ rules-v1 thresholds 0.60/0.30 defaults | §12/§26 calibrated on labeled validation set | No labeled citation dataset; thresholds arbitrary | Verdicts may mislabel borderline cases | Author labeled citation cases; run harness sweep |
| 3 | Evaluation datasets | ❌ empty (runner + math tested) | §26 golden set ~30–50 notes + labeled claims/queries | No cases authored | Quality regressions undetectable | Seed golden set during Phase 7 features |
| 4 | Orchestration framework | 🟡 explicit sequential functions | §31-40 LangGraph pipeline | No graph runtime (retries between nodes, branching) | Linear flow only — matches current needs | Adopt langgraph when conditional/looping nodes appear |
| 5 | Evidence retrieval ordering in enrichment | Index order, not relevance-ranked | §51 retrieve *relevant* chunks | No per-topic ranking into stage A | Large documents may draft from unrepresentative chunks | Reuse RRF scoring for evidence selection |
| 6 | Coalescing window / quota budgets | ❌ manual refresh only | §21/§74 scheduling + budgets | No automatic re-enrichment; no spend caps | Cost control unenforced | Implement with real LLM costs at Phase 8 |
| 7 | Multiple citations per block | One CitationBlock w/ refs array | §12 shape matches | Refs array is the spec shape ✓ but per-ref verdicts collapse to block-level | Granular attribution limited | Split rows if per-ref verdicts required |
| 8 | Enrichment of reference docs | Blocked by guard | n/a (users enrich own notes) | Intentional | — | None |
| 9 | Frontend AI Classroom UI | ❌ API-only this phase | §63 ai-classroom feature | Users cannot see enrichment without curl | Feature invisible end-user side | Build with Phase 7 alongside tests/chat UIs |

## Non-limitations (deliberate)

- Sequential orchestration without LangGraph (F-003).
- Overview blocks honestly flagged unsupported by the verifier.
- Supersede-and-retain enrichment history (F-007).
