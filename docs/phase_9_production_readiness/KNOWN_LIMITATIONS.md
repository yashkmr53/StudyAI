# Known Limitations — Final Production Audit

Every limitation is classified with evidence and a concrete next step. Items marked **BLOCKER** prevent production go-live; others are quality/operational improvements.

---

## Go-live blockers

| # | Limitation | Evidence | Impact |
|---|---|---|---|
| 1 | RLS not enforced under actual deployment role | Dev DB role `yash` is superuser → PostgreSQL bypasses RLS by design. Behavioral probe via `SET ROLE rls_probe` confirmed fail-closed scoping works when role is restricted, but no environment currently connects as restricted role | Isolation rests entirely on application-layer queryset filtering in every tested configuration. A single scoping bug would be unmitigated at the DB level |
| 2 | Mock AI providers produce synthetic content end-to-end | `MockOCRProvider` returns "Recognized line N: …" fabrications; `MockLLMProvider` restructures evidence without reasoning. No real provider API keys exist or are configured | All downstream artifacts (enrichment, citations, questions, chat answers) contain fabricated content. Product value for real users = zero until §30 providers selected |
| 3 | No scheduled backup automation | `backup_database` and `verify_backup` commands exist and were drilled successfully (159 KB dump restored into scratch DB with matching row counts), but nothing invokes them periodically. No offsite copy exists | Data-loss window between manual backups is infinite |

## Pre-production requirements (not blockers for internal testing)

| # | Limitation | Evidence |
|---|---|---|
| 4 | TLS termination unverified — nginx.conf has no HTTPS server block; prod.py sets SECURE_SSL_REDIRECT but no cert provisioned | 🟡 |
| 5 | Compose stack containers start but full functional E2E through nginx proxy incomplete | 🟡 healthz/readyz pass through proxy; register/upload/search not yet re-verified through compose |
| 6 | CI workflow authored (.github/workflows/ci.yml) but never executed on GitHub | ⚠️ |
| 7 | Coverage measurement tooling absent | Unknown % test coverage |
| 8 | Password-reset email dispatch stubbed | Endpoint returns 202 always; no token model, no email backend |
| 9 | Distributed throttle cache absent | DRF throttling uses LocMemCache per process; multi-node counters independent |
| 10 | Prompt-injection defenses structural only | Evidence wrapped as JSON to mock LLM; real-LLM injection surface untested |
| 11 | Object storage is local FS variant | No S3-compatible implementation; single-host storage only |

## Quality/calibration gaps

| # | Item | Detail |
|---|---|---|
| 12 | Verifier thresholds uncalibrated | supported ≥0.60 / partially ≥0.30 are arbitrary defaults, not derived from labeled data |
| 13 | Mastery EMA constants untuned | gain=0.4, decay=0.4, confidence default=0.75 are engineering guesses |
| 14 | Planner weights untuned | weakness=0.45, urgency=0.25, failures=0.20, insufficient=0.10 are set, not measured |
| 15 | Embedding model lexical-grade only | Hashing embedder cannot match semantic paraphrases; CJK tokens untokenized |
| 16 | Golden evaluation dataset absent | §26 requires ~30–50 notes + labeled claims/retrieval/citation cases; zero cases authored |
| 17 | Retrieval reranking stage absent | Explicitly optional for v1; fusion-only ranking may be suboptimal |
| 18 | Chunk sizing word-based not token-based | Fixed 120-word target; model-token alignment would improve embedding quality post-swap |

## Operational gaps

| # | Limitation | Detail |
|---|---|---|
| 19 | Health endpoints exist but no external monitoring/alerting wired | No Prometheus/Grafana/Sentry/PagerDuty integration |
| 20 | Metrics histogram resets on process restart | In-memory deque; no persistent time-series store |
| 21 | Reaper function defined but nothing schedules it automatically | Requires beat schedule or cron entry at deploy time |
| 22 | Object storage GC absent | Superseded PDFs and orphaned uploads accumulate indefinitely |
| 23 | Tag rename API absent | RenameTag service exists but no REST endpoint exposes it |
| 24 | Learning-feature frontend screens missing | Tests/chat/planner API-complete but no UI built |
| 25 | Coverage measurement not configured | No coverage.py or equivalent in CI/local workflow |

## Deliberate deviations from spec letter

These are documented design decisions, not defects:

1. Sequential pipeline functions instead of LangGraph dependency
2. revision_ids JSON list instead of singular FK on EnrichedNote/NoteChunk
3. Signed-URL JSON payload instead of HTTP redirect on download endpoint
4. Budget-as-call-count proxy for cost tracking until real provider pricing known
5. Local-FS storage instead of S3 for v1 development
6. Hashing embeddings as deterministic placeholder until neural model adopted
7. Trailing-slash-less URLs matching spec §60 exactly
8. 422 validation remap of DRF's default 400 per spec §61
9. Server-side SyncOperation table replaced by stroke-level idempotency keys
