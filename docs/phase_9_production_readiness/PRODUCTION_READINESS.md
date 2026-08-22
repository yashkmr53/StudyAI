# Production Readiness Audit — StudyAI v4.1

**Audit date:** 2026-08-22
**Auditor:** Automated + manual evidence-based review
**Architecture:** v4.1 (`StudyAI_app_architecture_v4_1_full.md`)
**Codebase state:** All 8 implementation phases complete

---

## VERDICT

```
PRODUCTION READY: NO
```

The system is **functionally complete and internally verified** (116 automated tests green, all core flows exercised end-to-end) but **not production-ready** due to: synthetic AI content (mock OCR/LLM), RLS enforcement unproven under the actual deployment role configuration, no scheduled backups, no TLS termination verified, and no CI execution evidence. These are deployment-infrastructure and provider-selection gaps, not code defects.

---

## Scorecard

| Area | Status | Evidence | Risk | Required Action |
|---|---|---|---|---|
| Authentication | ✅ VERIFIED | 116 tests incl. auth suite; JWT rotation+blacklist live; E2E login/register/logout via running stack | Low | — |
| Authorization / isolation | ✅ VERIFIED | Cross-user probes: every foreign access → 404; write attempts → 403/404 | Low | — |
| RLS policies exist | ✅ VERIFIED | `pg_policies` query returned 24 policies across 23 tables | — | — |
| **RLS behavioral enforcement** | 🟡 VERIFIED at SQL level, 🟡 app-path untested | Restricted-role probe: fail-closed without GUC, scoped with GUC, wrong-GUC isolated. App-path requires Django connected as non-superuser — not yet configured in dev/prod settings | HIGH if prod uses superuser role | Configure prod DB role as non-superuser; re-run probe |
| Migration from zero | ✅ VERIFIED | Fresh DB + restricted role → all 45 tables, 24 policies, HNSW index created. Extension pre-create required superuser (documented) | Medium: extension privilege must be provisioned by DBA on managed PG | Document extension pre-install step for managed PG providers |
| Canvas fencing | ✅ VERIFIED | Takeover gen=2 → stale gen=1 write → 409 SESSION_LOCK_LOST; heartbeat/expiry tested | Low | — |
| NoteSpace PDF | ✅ VERIFIED | Live generation through stack: valid %PDF-1.3 output (~15 KB); immutable content-addressed artifacts; old retained on regen | Low | — |
| Object storage | ✅ VERIFIED | Signed URL roundtrip (PUT→200, GET→bytes); forged token → 403; magic-byte sniffing → 422 on mismatch | Medium: local-FS only; no S3 variant implemented | Implement S3-compatible provider before multi-node deploy |
| Rate limiting | ✅ VERIFIED | Auth scope throttled to 429 RATE_LIMITED envelope after 3/min; ai scope 120/min; flag-gated per environment | Low once enabled in prod | Ensure `RATE_LIMITING_ENABLED=True` in prod env |
| Audit logging | ✅ VERIFIED | Register/login/logout/document.created events written to DB; staff-only listing endpoint functional | Low | Extend event coverage as features grow |
| Daily AI budget | ✅ VERIFIED | Budget=1 → first enrich/chat OK → second → 429 RATE_LIMITED; NoteSpace unaffected | Low | Set real budget value based on provider costs |
| Provider fallback chain | ✅ VERIFIED | OCR chain (Phase 3); LLM chain (Phase 8): failing primary → mock fallback succeeds; attempted chain recorded | Mechanism proven; providers 🔧 mock | Select real OCR/LLM providers (§30 decision) |
| Health endpoints | ✅ VERIFIED | /healthz 200 always; /readyz 200 with DB probe; 503 when DB down | Low | Wire into load-balancer health check |
| Internal status page | ✅ VERIFIED | /api/v1/status returns jobs/providers/citations/requests aggregates (staff only) | Low | — |
| Magic-byte upload sniffing | ✅ VERIFIED | Fake PNG body rejected 422; real PNG accepted 200 | Low | — |
| Security headers | ✅ VERIFIED | X-Content-Type-Options, Referrer-Policy, Permissions-Policy present on responses | Low | Add CSP at frontend serving layer |
| Search / retrieval | ✅ VERIFIED | POST /search returns scoped results w/ dense+keyword+RRF scores; cross-profile zero results | Low quality: embeddings lexical-grade | Swap embedding model for semantic matching |
| Enrichment pipeline A–F | ✅ mechanics / 🔧 LLM text | Full pipeline through deployed stack: draft+gap+fill blocks persisted w/ citations+verdicts | HIGH: content is synthetic until real LLM selected | Select real LLM provider; implement protocol impl; swap registry entry |
| Evidence verifier | ✅ mechanism ⚠️ thresholds | rules-v1 lexical support; supported ≥0.60 / partially ≥0.30; discriminating verdicts observed | Medium: thresholds arbitrary without calibration | Author labeled citation dataset; calibrate |
| Question generation | ✅ mechanics 🔧 text | MCQs generated bound to revision+chunk; stale propagation works | Content synthetic until LLM swap | — |
| Adaptive test selection | ✅ VERIFIED | Deterministic priority ordering asserted; same state ⇒ same selection | Low | Tune weights after real usage data |
| Mastery scoring | ✅ VERIFIED | EMA formula deterministic; attempt+score atomic; not_assessed ≠ zero | Constants untuned | Calibrate from accumulated attempts |
| Chatbot | ✅ mechanics 🔧 answer text | Scoped retrieval + grounded extractive answer + verified citations persisted | Answer quality limited by mock LLM + hashing embeddings | Requires real LLM + neural embeddings |
| Revision planner | ✅ VERIFIED | Deterministic weakness/urgency/failures/insufficient scoring; ≤14-day schedule; goals persisted | Low | — |
| Tag hierarchy + changelog | ✅ VERIFIED | Stable identity across renames; ADDED/LINKED/RENAMED logged; subject-less docs skip | Low | Expose rename API in hardening |
| Celery/Redis broker | 🟡 IMPLEMENTED—NOT VERIFIED | Worker container starts, connects to Redis, but full task round-trip not yet demonstrated end-to-end | Medium: async processing unproven under broker | Run compose stack drill with worker consuming tasks |
| Docker/deploy artifacts | 🟡 IMPLEMENTED—NOT VERIFIED | Compose config VALID; containers built and started; but full-stack functional smoke incomplete | Medium: runtime integration issues possible | Execute clean-host compose up drill |
| TLS | 🟡 IMPLEMENTED—NOT VERIFIED | nginx.conf authored; prod.py SSL redirect env-tunable; SECURE_PROXY_SSL_HEADER set | No domain/cert available locally | Obtain cert; verify HTTPS redirect + secure cookies |
| Backup automation | ❌ MISSING | Commands exist; manual drill performed; nothing schedules them automatically | HIGH: data loss window = ∞ | Add cron/systemd timer + offsite copy |
| Golden eval dataset | ❌ MISSING | §26 requires ~30–50 notes + labeled cases | Quality regressions undetectable | Author before Phase 7 features go user-facing |
| Verifier calibration | ❌ NOT DONE | Thresholds 0.60/0.30 are defaults, not calibrated | Citation verdicts may mislabel | Calibrate using golden dataset |
| Embedding model | 🟡 HASHING placeholder | §2 mandates local model; hashing is lexical-grade only | Semantic retrieval weak | Adopt sentence-transformers or similar |

---

## Final counts

```text
Total requirements tracked:      111
VERIFIED (executed evidence):     58
IMPLEMENTED — NOT VERIFIED:       12
PARTIAL:                           9
MISSING:                          13
DEFERRED / NOT APPLICABLE:         2
MOCKED/SYNTHETIC components:       6

Tests:   backend 116 total (116 pass PG / 113 pass + 3 skip SQLite)
         frontend 1 vitest pass; build green
Failing: 0
Skipped: 3 (SQLite-only runs; PG-only tests execute under dev profile)
```

## GO-LIVE BLOCKERS

1. **RLS enforcement under restricted role not wired into deployment config** — dev/test use superuser which bypasses RLS entirely. Must configure a non-superuser DB role and re-run behavioral probe.
2. **Mock AI providers produce synthetic content** — OCR text is fabricated, enrichment echoes it. Real providers must be selected and integrated.
3. **No scheduled backup automation** — commands exist and were drilled manually, but nothing runs them periodically. Data-loss window is infinite.

## NON-BLOCKING RISKS

1. Distributed throttle store absent (single-node rate limiting only).
2. Metrics histogram resets on process restart (in-memory).
3. Prompt-injection defenses become behavioral only at real-LLM swap.
4. Password-reset email flow stubbed.
5. Coverage measurement not configured.
