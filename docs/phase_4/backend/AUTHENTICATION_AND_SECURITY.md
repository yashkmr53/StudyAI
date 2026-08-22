# Authentication and Security — after Phase 4

Base model unchanged (see [`../phase_3/backend/AUTHENTICATION_AND_SECURITY.md`](../../phase_3/backend/AUTHENTICATION_AND_SECURITY.md)). Phase 4 additions:

| Concern | Mechanism | Code |
|---|---|---|
| PDF artifact isolation | Querysets join `document__profile__user`; foreign IDs → 404 | `DigitizedDocumentViewSet`, `NoteSpaceService.get_owned_artifact` |
| Authz before signed URL | Ownership verified, then object existence, then URL minted | `DigitizedDownloadView` |
| Short-lived access | Download URLs expire after `SIGNED_URL_TTL_SECONDS` (300 s); action+key bound in HMAC payload | `LocalObjectStorage._sign/verify` |
| Render job abuse | Content-addressed idempotency: repeated identical requests return the existing artifact instead of re-rendering | `request_pdf` + unique constraint |
| Faithfulness as security | Renderer has no LLM/provider imports; cannot inject or alter content | `pdf_renderer.py` import surface |

## How User A is kept out of User B's PDFs

1. A cannot resolve B's artifact ID (404 — queryset filtered by owner).
2. Even knowing the storage key, downloads require a validly signed URL which only an ownership-checked endpoint mints.
3. RLS policy on `documents_digitizeddocument` EXISTS-chains to the document profile (fail-closed GUC); same dev-superuser caveat as all phases.

Open items unchanged: rate limiting ❌ · audit logging ❌ · password-reset email 🔧 · localStorage tokens · restricted-role RLS behavioral test.
