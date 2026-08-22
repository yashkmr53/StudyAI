# Authentication and Security — after Phase 2

Phase 1 security model is unchanged and documented in [`../phase_1/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_1/backend/AUTHENTICATION_AND_SECURITY.md). This page records what Phase 2 adds.

## New enforcement points (canvas)

| Concern | Mechanism | Code |
|---|---|---|
| Session ownership | Session queryset filters `profile__user=request.user`; foreign IDs → 404 | `CanvasSessionService.get_owned_session` |
| Profile reference on create | `ProfileAuthorizationService.ensure_profile_access` before insert | `CanvasSessionViewSet.create` |
| Single-writer integrity | Every mutating call validates `lock_holder == device_id && lock_generation == current && unexpired`, under a row lock on the session | `CanvasSessionService.ensure_lock` + `select_for_update` in all write paths |
| Stale-writer fencing | Takeover increments generation; old generation ⇒ `409 SESSION_LOCK_LOST` | `takeover()`, tested |
| Immutability after finalize | Finalized pages reject stroke writes with `409 REVISION_CONFLICT`; finalize is idempotent | `append_strokes`, `finalize_page` |
| Replay protection | Unique `client_idempotency_key` per stroke; duplicates reported, never re-inserted (savepoint create keeps the batch alive) | `append_strokes`, replay test |
| Row-level security | Policies on all three canvas tables keyed to the session's profile via direct column or EXISTS chain | `canvas/0002_enable_rls.py` |

## How User A is kept out of User B's canvas data

1. **API layer:** every canvas queryset joins through `session__profile__user=request.user`. A cannot even resolve B's session/page/stroke IDs (404).
2. **Write layer:** A creating a session under B's profile → 403; any write without a currently valid lock (holder+generation+expiry) → 409.
3. **Database layer:** RLS policies compare the row's profile lineage against the transaction-local GUC; unset context fails closed. Same superuser caveat as Phase 1: dev role bypasses RLS; app-layer isolation is active and tested.

## Threat-model additions covered in Phase 2

| Threat (§71) | Mitigation now real |
|---|---|
| Stale canvas device | Fencing generations + expiry + takeover (tested) |
| Job replay / duplicate writes | Stroke-level idempotency keys with DB unique constraint (tested) |

## Unchanged open items

Rate limiting ❌ · audit logging ❌ · password-reset email 🔧 · tokens in localStorage (frontend) · CORS/CSRF posture dev-only · file validation n/a until ingestion · RLS behavioral test as restricted role pending.

No new secrets or credentials were introduced by Phase 2. Repository secret scan remains clean.
