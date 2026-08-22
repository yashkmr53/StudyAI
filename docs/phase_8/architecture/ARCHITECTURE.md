# Architecture — Final System Status after Phase 8

All 8 phases implemented. Delta documentation for Phases 1–7: [`../phase_7/architecture/ARCHITECTURE.md`](../../phase_7/architecture/ARCHITECTURE.md).

## Complete module status

| Module / Layer | Status |
|---|---|
| Security foundation (auth, RLS on 23 tables, error contract, throttles, audit) | ✅ |
| Canvas + offline sync | ✅ |
| Shared ingestion | ✅ (OCR providers 🔧 mock) |
| NoteSpace (Module 1) | ✅ |
| AI Classroom foundation + intelligence + learning layer | ✅ mechanics 🔧 LLM text 🟡 hashing embeddings |
| Hardening: fallback chain, health/status/metrics, budgets, regression gate, backup drill, CI, deploy artifacts | ✅ / 🟡 as noted |

## New backend components (Phase 8)

```text
apps/audit/
├── models.py        # AuditLog · ProviderCallLog
├── services.py      # audit() best-effort writer
├── views.py         # staff listing GET /api/v1/audit?action=…
└── management/commands/
    ├── backup_database.py
    └── verify_backup.py
providers/llm/{chain,failing}.py   # LLMChainProvider + always-fail test provider
shared/throttles.py                # LiveSettingsScopedRateThrottle + enable flag
shared/observability/
├── metrics.py                     # registry + TimingMiddleware + SecurityHeadersMiddleware
└── views.py                       # HealthzView · ReadyzView · StatusView (staff)
config/settings/ci.py              # CI profile (PG container)
```

## Ops flows implemented

- **Health**: `/healthz` liveness; `/readyz` DB probe.
- **Status page** (`/api/v1/status`, staff): job health by status/type, queue depth, dead-letter + retryable backlog, 24 h created/retried, provider usage from ProviderCallLog, citation verdict distribution, request p50/p95/p99.
- **Fallback**: LLMChainProvider primary→fallback with per-attempt telemetry; OCR chain unchanged.
- **Budgets**: enrich/chat gated by per-profile daily call budget → 429 RATE_LIMITED; graceful degradation keeps NoteSpace and reads alive.

## Invariants honored (new this phase)

| Invariant | How it holds |
|---|---|
| Provider SDKs isolated behind interfaces (§32 #22) | chain/mock/failing behind `LLMProvider` |
| Graceful degradation when AI unavailable (§28) | budget gate returns 429; NoteSpace untouched |
| Audit trail without breaking user flows (§23) | audit() never raises |

## Component inventory — final

| Area | Status |
|---|---|
| All product modules & pipelines | ✅ (AI content 🔧 mocks) |
| Hardening: throttles/audit/headers/sniffing/budgets/regression gate | ✅ |
| Observability endpoints | ✅ v1 scope (external APM ❌) |
| Backup commands + verified drill | ⚠️ automation ❌ |
| CI workflow | ⚠️ authored, unexecuted |
| Deployment artifacts | 🟡 authored, host drill pending |
