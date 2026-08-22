# Authentication and Security — after Phase 5

Base model unchanged (see [`../phase_4/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_4/backend/AUTHENTICATION_AND_SECURITY.md)). Phase 5 additions:

## New enforcement points

| Concern | Mechanism | Code |
|---|---|---|
| Retrieval isolation | Search base queryset filters `Q(profile_id__in=user_profiles) \| Q(profile_id__isnull=True)` — own chunks plus platform reference rows only | `apps/retrieval/retrieval.py::_base_queryset` |
| Reference READY gating | Join filter + defensive read-time check: non-READY books never surface even if chunk rows exist | `RetrievalService.search` |
| Stale content exclusion | `stale=false` filter — superseded transcription is not retrievable | same |
| Subject scoping | Optional subject filter validated against the caller's subjects | `SearchView` |
| Chunk RLS | Policy `(profile_id::text = GUC OR profile_id IS NULL)` — user rows fail-closed on unset GUC; platform rows readable | `retrieval/0003_enable_rls.py` |

## How User A is kept out of User B's indexed content

1. Search base queryset resolves the caller's profile IDs from the authenticated user and filters chunks by them.
2. RLS policy mirrors this at the database layer (same superuser-bypass caveat in dev).
3. Reference chunks are platform-wide by design but read-only and gated on book status.

## Threat-model additions covered

| Threat (§71) | Phase 5 mitigation |
|---|---|
| Cross-profile data leakage through retrieval | SQL-level scoping tested (`test_profile_isolation`) |
| Prompt-injection via retrieved evidence | Not yet applicable — no LLM consumer exists; §72 wrapping planned with enrichment/chat |

## Still open

Rate limiting ❌ · audit logging ❌ · restricted-role RLS behavioral test · search endpoint rate limits when chat lands.
