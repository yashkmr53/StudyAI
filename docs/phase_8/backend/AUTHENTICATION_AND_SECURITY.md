# Authentication and Security — after Phase 8

Base model unchanged ([`../phase_6/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_6/backend/AUTHENTICATION_AND_SECURITY.md)). Phase 8 closes several §23/§71 items:

| Concern | Mechanism | Code |
|---|---|---|
| Rate limiting | DRF scoped throttles: `auth` 30/min on all auth endpoints; `ai` 120/min on search/enrich/chat-messages. Live-settings subclass reads rates at call time | `shared/throttles.py` + view declarations; 429 envelope verified by test |
| Malicious uploads (§71) | Magic-byte signature validation against declared type → 422 envelope; size cap unchanged | `providers/storage/views.py::_magic_matches` |
| Audit trail (§23) | AuditLog rows for auth lifecycle + document creation (+ extensible service); staff-only listing with action filter; actor SET_NULL + email snapshot survives deletion | `apps/audit/**`, wired in accounts/documents views |
| Security headers | nosniff, Referrer-Policy, Permissions-Policy middleware (X-Frame-Options via Django middleware) | `shared/observability/metrics.py::SecurityHeadersMiddleware` |

## How User A is kept out of User B's data — status after Phase 8

Unchanged two-layer model (app-layer scoping + RLS policies now covering **23 tables**), plus:

1. Throttles blunt credential-stuffing and AI-cost abuse (`429 RATE_LIMITED` envelope).
2. Chat/planner/search evidence assembly is bounded to the caller's profile IDs before any ranking happens.
3. Audit entries give post-hoc traceability of auth lifecycle and document creation with IP capture.

Standing caveats (unchanged): RLS bypassed by dev superuser role; distributed throttle store needed beyond single node; password-reset email still stubbed.
