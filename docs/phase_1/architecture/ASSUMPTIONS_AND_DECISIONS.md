# Assumptions and Decisions

Every engineering decision **not explicitly determined by the v4.1 architecture**. Format: ID · Decision · Context · Why · Alternatives · Consequences · Architecture impact.

| ID | Decision |
|---|---|
| A-001 | `myenv/` (Python 3.14) at repo root is the single Python environment for all backend work. |
| A-002 | Django 6.1 + DRF on Python 3.14. |
| A-003 | PostgreSQL 18 via Homebrew; dev connects over unix socket `/tmp` as user `yash` (superuser). |
| A-004 | Custom user model with email login, UUID PKs on all domain models. |
| A-005 | SimpleJWT with 30-min access / 14-day refresh, rotation + blacklist enabled. |
| A-006 | Frontend persists JWTs in `localStorage`. |
| A-007 | Argon2 primary password hasher. |
| A-008 | Registration auto-creates a Profile named `"Default"`. |
| A-009 | DRF validation errors remapped to HTTP 422 `VALIDATION_ERROR`. |
| A-010 | Trailing-slash-less API URLs; page-number pagination (size 50); JSON-only renderer. |
| A-011 | RLS: `ENABLE` without `FORCE`; policies compare `profile_id::text` to GUC; dev superuser bypasses. |
| A-012 | Unit tests run on SQLite (`config.settings.test`); Postgres-specific tests skip there and run under dev settings. |
| A-013 | Object storage = local filesystem provider with HMAC-signed expiring URLs; S3 deferred. |
| A-014 | Celery configured but no tasks/worker; Redis not installed; tests use eager in-process mode. |
| A-015 | `Job.profile_id` is a plain UUID column, not a FK. |
| A-016 | Password reset is an enumeration-safe stub (202 always), no email backend. |
| A-017 | Frontend stack: Vite + React 19 + TS, zustand, react-router v7 (declarative mode), idb, fetch wrapper (no axios/react-query). |
| A-018 | Vite dev proxy `/api → 127.0.0.1:8000`; no CORS layer in dev. |
| A-019 | Outbox `client_sequence` uses `Date.now()` instead of a monotonic per-device counter. |
| A-020 | OpenAPI generated code-first with drf-spectacular and committed to docs. |

---

## Details

### A-001 — Central virtualenv
- **Context:** User directive; repo ships `myenv/`.
- **Why:** One env for all Python tooling; avoids system pollution.
- **Alternatives:** per-app venvs, Poetry/uv, Docker-only.
- **Consequences:** All commands must use `./myenv/bin/python`; Python 3.14 is bleeding-edge (some packages lag).
- **Architecture impact:** None.

### A-002 — Django 6.1
- **Context:** Latest Django supporting the features needed; installed cleanly on 3.14.
- **Why:** Spec §23 mandates mature Django auth infrastructure.
- **Alternatives:** Django 5.x LTS (more conservative), FastAPI (rejected — spec names Django+DRF).
- **Consequences:** Newer framework line; LTS migration path straightforward.
- **Architecture impact:** None — spec-compliant.

### A-003 — Local Postgres 18, socket auth, superuser role
- **Context:** Machine already runs Homebrew `postgresql@18`.
- **Why:** Zero-config local dev.
- **Alternatives:** Dockerized Postgres (deferred to deployment work).
- **Consequences:** **Dev role bypasses RLS** (superuser exemption). RLS policies verified structurally but not enforced locally. Production must use a non-superuser role.
- **Architecture impact:** Deviation in *enforcement environment only*, not design.

### A-004 — Email login + UUID PKs
- **Why:** Modern UX; non-enumerable IDs needed later for signed URLs and offline-created canvas objects.
- **Alternatives:** username login; BigAutoField PKs.
- **Consequences:** Custom user model must be the first migration (done).
- **Architecture impact:** Consistent with §66 constraint examples.

### A-005 — JWT parameters
- **Why:** Short access window limits stolen-token utility; rotation makes replay detectable (§23 revocation requirement).
- **Alternatives:** opaque session tokens; PASETO.
- **Consequences:** Blacklist tables add two migrations; logout revokes refresh only, access expires naturally ≤30 min.
- **Architecture impact:** Implements §23 revocation strategy.

### A-006 — Tokens in localStorage
- **Why:** PWA reload persistence without cookie infrastructure.
- **Alternatives:** httpOnly cookie refresh token (stronger XSS posture; needs CSRF handling + same-site deployment).
- **Consequences:** XSS would expose tokens. Mitigation path documented in KNOWN_LIMITATIONS.md.
- **Architecture impact:** None in spec; security trade-off recorded.

### A-009 — 422 for validation
- **Context:** DRF default is 400; spec §61 defines `422 VALIDATION_ERROR`.
- **Implementation:** exception handler converts `DRFValidationError` → domain `ValidationError`.
- **Consequences:** Clients must treat 422 as the validation signal.
- **Architecture impact:** Aligns API with spec contract.

### A-011 — RLS enable-without-force
- **Why:** Keeps table-owner migrations/admin workable; superusers bypass regardless of FORCE.
- **Alternatives:** FORCE ROW LEVEL SECURITY + dedicated non-owner app role now.
- **Consequences:** Enforcement depends on deployment using a restricted role (production checklist item).
- **Architecture impact:** Policy design matches §3 exactly; enforcement posture differs in dev.

### A-014 — Celery configured, not running
- **Why:** Phase 1 has no async work; installing Redis adds nothing yet.
- **Consequences:** `CELERY_BROKER_URL` default points at a Redis that isn't there; harmless until tasks exist. Tests run eager.
- **Architecture impact:** Job state stays in PostgreSQL either way (spec §32 #12).

### A-015 — Job.profile_id as plain UUID
- **Why:** Avoids premature cascade-deletion decisions (§66 warns against cascading historical records); RLS keys off the value regardless.
- **Alternatives:** FK with SET NULL / RESTRICT.
- **Consequences:** No referential integrity from jobs → profiles; acceptable while no producers exist.
- **Architecture impact:** None — spec shows `profile_id` on Job without specifying FK semantics.

### A-017 — Minimal frontend deps
- **Why:** Fetch wrapper + zustand cover current scope; axios/react-query add surface without need yet.
- **Consequences:** Client implements its own refresh-retry (single retry) and error parsing.
- **Architecture impact:** None.

### A-019 — client_sequence simplification
- **Context:** Spec's outbox defines `client_sequence` for ordering.
- **Current:** `Date.now()` at enqueue time.
- **Risk:** Two ops in the same millisecond could tie; server ordering should not rely on it until replaced by a monotonic counter.
- **Next step:** per-device incrementing counter persisted in IndexedDB when canvas sync lands (Phase 2).

### Deferred decisions (spec §30 open items)
OCR provider, hosting, reference-book scope, change-magnitude threshold, golden-set process, LLM models, OCR retention, manual OCR editing, citation thresholds — **all undecided**, none blocking current phases.
