# Known Limitations — after Phase 2

Carried-over Phase 1 limitations remain documented in [`../phase_1/KNOWN_LIMITATIONS.md`](../phase_1/KNOWN_LIMITATIONS.md) (RLS superuser bypass, no rate limiting, password-reset stub, localStorage tokens, storage serving views, Celery idle, pgvector absent, health endpoints, audit logging, metrics, backups, CI, deployment artifacts, OpenAPI warnings, coverage unmeasured).

## New or changed in Phase 2

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | Finalize downstream work | ⚠️ Lock validation + finalization only | §67: finalize + document revision + OCR job in one transaction | Revision/job creation deferred to Phase 3 | Finalized pages aren't yet source documents | Implement ingestion models; extend `finalize_page` transaction |
| 2 | Outbox failure states | 🟡 Failed ops stay `pending`; retried forever | §4 failed → retrying → sending with backoff | No persisted failure state, no dead-letter | A poison op retries indefinitely per flush | Persist failure counts + exponential backoff + give-up threshold |
| 3 | Flush debounce | 🟡 Interval + per-stroke trigger instead of pause-debounce | §4 "debounce sync after stroke pauses" | No explicit debounce timer | Slightly chattier sync than spec's ideal | Add trailing-edge debounce if traffic warrants |
| 4 | Server-side SyncOperation records | 🟡 Replaced by stroke-level idempotency keys (B-001) | §29 diagrams SyncOperation entity | No server-side op audit trail | Replay protection works; raw-op audit absent | Add op log table only if audit requirement emerges |
| 5 | Stroke metadata | Points only | Rich ink (color/width/pressure) | No styling fields | All notes render identically | Extend stroke schema when stylus support is planned |
| 6 | Canvas concurrency tests | Fencing logic tested via row states | §68 race coverage on real PG | SQLite ignores FOR UPDATE; no PG concurrency suite | Theoretical race windows unproven | PostgreSQL-based concurrency tests in CI |
| 7 | Editor test automation | Manual E2E only | Tested offline-sync behavior | No vitest/playwright for editor/outbox | Regressions caught manually | Playwright E2E for capture→sync→fencing flows |
| 8 | Multi-tab same device | Shared device_id across tabs | Single-writer semantics | Tabs fence each other via takeover | Confusing UX in one browser | Per-tab device sub-id or session-level tab lock UX |

## Non-limitations (deliberate, recorded in decisions)

- Batched strokes endpoint with mixed create/duplicate outcomes (B-008).
- Forced takeover for the owning user (B-003).
- 409 REVISION_CONFLICT for post-finalize writes (B-009).
