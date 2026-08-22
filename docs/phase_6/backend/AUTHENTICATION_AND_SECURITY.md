# Authentication and Security — after Phase 6

Base model unchanged (see [`../phase_5/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_5/backend/AUTHENTICATION_AND_SECURITY.md)). Phase 6 additions:

| Concern | Mechanism | Code |
|---|---|---|
| Enrichment isolation | Latest-note lookup + enqueue scoped through `document__profile__user`; foreign → 404 | `EnrichmentService`, DocumentViewSet actions |
| Generated-layer RLS | EXISTS-chain policies on enriched notes/blocks/citations keyed to the document's profile | `ai_classroom/0002_enable_rls.py` |
| Reference-doc protection | Platform reference documents (profile NULL) are rejected for enrichment; users cannot modify them anywhere | `enqueue_enrichment` guard |
| Prompt-injection posture | Evidence passed to the (mock) LLM as JSON data blocks; no instruction channel exists yet. §72 wrapping becomes behavioral at real-LLM swap | pipeline evidence payload |
| Data minimization before provider calls (§73) | Only chunk ids + contents of the target document are serialized into evidence — no user identity, tokens, or unrelated rows | `run_enrichment_job` |

## How User A is kept out of User B's enrichment data

1. API: latest-note and enrich actions resolve the document via owner-scoped querysets (foreign → 404).
2. DB: RLS EXISTS chains on all three generated-layer tables.
3. Jobs: enrich jobs carry profile_id from server-side document lookup; executor binds RLS context from that trusted value.

## Still open

Rate limiting ❌ · audit logging ❌ · password-reset email 🔧 · localStorage tokens · restricted-role RLS test · prompt-injection behavioral defenses once a real LLM consumes arbitrary note text.
