# Authentication and Security — after Phase 3

Phase 1/2 model unchanged: JWT rotation+blacklist, app-layer authorization, RLS, fencing. See [`../phase_1/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_1/backend/AUTHENTICATION_AND_SECURITY.md) and [`../phase_2/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_2/backend/AUTHENTICATION_AND_SECURITY.md). This page covers Phase 3 additions.

## New enforcement points

| Concern | Mechanism | Code |
|---|---|---|
| Document/page isolation | Querysets join through `profile__user=request.user`; foreign IDs → 404 | `IngestionService.get_owned_document/get_owned_page`, ViewSet querysets |
| Job isolation (plain-UUID column) | `profile_id__in` user's profiles; no FK traversal possible | `JobViewSet.get_queryset`, `CancelJobView` |
| Signed-URL authorization | Token signature + expiry + action + key must all match; token *is* the credential for storage views | `LocalObjectStorage.verify`, `StorageUploadView/DownloadView` |
| Upload validation (§23) | Content-type allow-list + size cap → 413/422 envelopes | `StorageUploadView` |
| Key namespace | Upload keys prefixed with profile id (`{profileId}/{pageId}.png`) enabling ownership-prefix checks when issuing URLs | `DocumentViewSet.create` |
| Worker RLS context | Handlers run inside `profile_scoped_transaction(job.profile_id)` using the trusted job payload, never client input | `run_claimed_job` (§47) |
| Revision immutability | Edits only create new revisions; service layer has no revision-mutation path | `_create_revision_locked` |

## How User A is kept out of User B's ingestion data

Documents, pages, revisions, and lines: queryset joins to the owner + RLS EXISTS-chain policies keyed on the document's profile (fail-closed GUC). Images: keys are unguessable UUID paths AND downloads require a signed URL that only an authorized issuer would produce; the signing path validates profile-prefix ownership before issuance in provider helpers. Jobs: explicit `profile_id__in` filter. Same superuser-bypass caveat as prior phases applies to RLS locally.

## Threat-model additions covered

| Threat (§71) | Phase 3 mitigation |
|---|---|
| Malicious file upload | Type allow-list + size cap + signed-target binding (key pinned in token) |
| Signed URL leakage | Short TTL (300 s), action+key bound into the HMAC-signed payload, forged/expired → 403 |
| Job replay / duplicate processing | Unique idempotency keys at creation + atomic claim + completed-revision short-circuit in handler |

## Still open (unchanged)

Rate limiting ❌ · audit logging ❌ · password-reset email 🔧 · localStorage tokens · CORS prod config · magic-byte content sniffing (type trust is header-based today) · RLS behavioral test under restricted role.
