# Known Limitations — after Phase 5

Carried over: [`../phase_4/KNOWN_LIMITATIONS.md`](../phase_4/KNOWN_LIMITATIONS.md) (RLS superuser bypass, rate limiting, password-reset stub, localStorage tokens, outbox failure states/debounce, stroke metadata, canvas concurrency + editor tests, multi-tab UX, OpenAPI warnings, coverage unmeasured, no CI/deploy artifacts/health endpoints/audit logging/backups, mocked OCR, image normalization, storage GC, magic-byte sniffing).

## New or changed in Phase 5

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | Embedding quality | 🟡 hashing embedder — lexical-grade | §2 local neural embeddings | No semantic paraphrase matching; no CJK tokenization (regex `[a-z0-9]`) | Retrieval misses semantic matches; non-latin content poorly embedded | Swap in bge-small/similar via sentence-transformers behind existing provider |
| 2 | Reranking stage | ❌ absent (spec-optional) | §14 optional reranker | Fused ranking only | Acceptable v1; revisit with LLM consumers | Evaluate after eval dataset exists |
| 3 | Fusion parameter tuning | k=60/depth=50 defaults | Calibrated retrieval | Untuned against data | Sub-optimal ordering possible | Tune on labeled retrieval set (§26) |
| 4 | Chunk sizing | Word-count based (120/30) | Token/model-aware chunking | Fixed words ≠ model tokens | Minor quality drift per model | Revisit at model swap |
| 5 | tsvector language config | Hardcoded `'english'` | Per-content language | Non-English stemming mismatched | Weak keyword recall for other languages | Make config per-document setting |
| 6 | Reference ingestion UI/command robustness | JSON file command; malformed input untested | Admin tooling | Failure paths manual | Operator friction only | Add validation + error reporting |
| 7 | Stale chunk pruning | Retained forever | §69 retention policy | Table growth per edit cycle | Storage drift | GC policy in hardening |
| 8 | Vector index maintenance | HNSW created at migration | Operational reindex strategy | No reindex tooling if dims/model change | Model swap needs column migration plan | Write model-swap migration recipe before F-001 swap |
| 9 | Search endpoint hardening | No throttle/cache | Production API | Unlimited query cost (bounded by local embedder today) | Trivial now, matters with chat | Throttle when chat lands |

## Non-limitations (deliberate)

- Keyword-only fallback on SQLite unit runs (E-010).
- Platform reference chunks visible to all authenticated users (§15 by design).
- `/search` beyond the original blueprint (F-004/E-009).
