# Authentication and Security — after Phase 7

Base model unchanged (see [`../phase_6/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_6/backend/AUTHENTICATION_AND_SECURITY.md)). Phase 7 additions:

| Concern | Mechanism | Code |
|---|---|---|
| Test/mastery isolation | Instance + mastery querysets filter `profile__user`; attempts nested through owned tests | `TestViewSet.get_queryset`, attempt action |
| Chat isolation | Session querysets owner-filtered; retrieval scoping makes cross-profile evidence unreachable; foreign sessions → 404 | `ChatSessionViewSet`, `ChatService.ask` |
| Planner isolation | Overview/plans resolve the caller's profile and intersect candidate tags with profile-linked documents | `RevisionPlanningService` |
| Answer integrity | `answer_index` never serialized before an attempt exists for that question in that test instance | `_serialize_test(include_answers=False)` default |
| Replay protection | Unique (test, question) + 409 IDEMPOTENCY_CONFLICT on duplicate attempts | DB constraint + explicit check |
| Generated/tag RLS | EXISTS-chain policies on tag/documenttag/changelog/questions/tests/attempts/mastery/chat/revision tables | `tests/0002_phase7_rls.py` |

## How User A is kept out of User B's learning data

1. Tests/attempts: every queryset joins `profile__user=request.user`.
2. Mastery rows: direct `profile_id` RLS policy plus app filtering.
3. Chat messages: session ownership gates message listing; retrieval scoping prevents B's chunks from ever entering A's context.
4. Tags: subject-anchored RLS chain (tags inherit their subject's profile).

## Still open

Rate limiting ❌ · audit logging ❌ · password-reset email 🔧 · localStorage tokens · restricted-role RLS behavioral test · chat rate limits.
