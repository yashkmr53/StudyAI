# Assumptions and Decisions — Phase 8

Prior decisions remain in force (A- through F-series in [`../phase_7/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../architecture/ASSUMPTIONS_AND_DECISIONS.md)). Phase 8 hardening decisions (H-series):

| ID | Decision |
|---|---|
| H-001 | LLM fallback mirrors the OCR chain: `LLMChainProvider` over a settings-driven provider list; chain returns the unified result object with `attempted_providers` attached (single shape for all callers). |
| H-002 | Metrics are an **in-process** registry + staff status endpoint — no external APM dependency; histogram capped at 2000 samples. |
| H-003 | Rate limiting uses DRF scoped throttles with a **live-settings subclass** (`shared/throttles.py`) so overrides/tests work despite DRF's import-time rate binding. |
| H-004 | `RATE_LIMITING_ENABLED` flag gates throttling globally: enabled by default, disabled in dev/test settings; the dedicated throttle test re-enables it with a LocMem cache override. |
| H-005 | Audit writes are best-effort (`audit()` never raises) and use SET_NULL actor FK + email snapshot so history survives user deletion. |
| H-006 | Daily AI budget counts enrich jobs + assistant chat messages per profile per UTC day as the spend proxy until real token accounting exists. |
| H-007 | Upload magic-byte sniffing validates PNG/JPEG/WebP signatures against the declared content type (closes header-trust gap). |
| H-008 | Backup drill = pg_dump plain file → restore into `<db>_restore_verify` scratch DB → row-count smoke query; live DB name is refused as target. |
| H-009 | Evaluation regression gate: `run_ai_evaluation --assert-gte metric=value` (repeatable) exits 2 when any metric falls below threshold — CI-ready. |
| H-010 | Load harness is stdlib-only (threads + urllib), reporting p50/p95/p99 against §75 targets; auth scenario capped at 50 requests to respect the throttle. |

---

## Details

### H-002/H-003 — Observability & throttle pragmatics
- **Why:** §25 asks for structured logs and a lightweight internal status page; DRF's class-level rate binding silently ignores test overrides.
- **Consequences:** metrics reset on restart (v1 scope); distributed deployments need a shared cache backend for throttles before scaling beyond one node.

### H-006 — Budget proxy
- **Why:** real cost needs token accounting from a live provider.
- **Semantics:** budget exhausted ⇒ 429 RATE_LIMITED envelope on enrich/chat; NoteSpace and all read paths unaffected (graceful degradation ✓).

### H-008 — Drill performed
- Executed `backup_database` → `verify_backup` against PostgreSQL: dump written (159,790 bytes), restored into scratch DB, smoke row-counts matched (documents=5, users=4). Output captured in CHANGELOG.

### Remaining known gaps after this phase
See [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md) — chiefly: calibration datasets, scheduled backup automation, managed-infra migration, and cloud deployment execution.
