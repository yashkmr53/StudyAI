# Authentication and Security

## Authentication mechanism

- **Type:** JWT bearer tokens (SimpleJWT) on every `/api/v1` endpoint except register/login/refresh/password-reset.
- **Access token:** 30 min. **Refresh token:** 14 days.
- **Rotation:** enabled — each refresh returns a new refresh token and blacklists the old one (`ROTATE_REFRESH_TOKENS`, `BLACKLIST_AFTER_ROTATION`).
- **Revocation:** `POST /auth/logout` blacklists the presented refresh token; blacklisted tokens fail at `/auth/refresh`. Access tokens simply expire (≤30 min exposure).
- Password hashing: Argon2 (`PASSWORD_HASHERS[0]`), PBKDF2 fallbacks for verification.

## Authorization model

```text
User ── owns ──> Profile ── scopes ──> Subjects (and all future resources)
```

Enforcement points, in order:

1. `JWTAuthentication` validates the bearer token → `request.user`.
2. Anonymous requests hit default `IsAuthenticated` → `401 UNAUTHENTICATED` envelope.
3. List querysets filter by ownership: `Profile.objects.filter(user=user)`, `Subject.objects.filter(profile__user=user)`.
4. Writes resolve referenced profiles through `shared/authorization/services.py::get_owned_profile` / `ensure_profile_access` → foreign profile ⇒ `403 FORBIDDEN`; unknown ⇒ `404`/`422`.
5. Database constraints (`unique(user,name)`, `unique(profile,name)`) are the final integrity layer.

## User isolation — exact answer to "How is User A prevented from accessing User B's data?"

| Layer | Mechanism | Code |
|---|---|---|
| API list/read | Querysets filtered by `request.user`; foreign IDs yield 404 | `apps/profiles/views.py`, `apps/subjects/views.py` |
| API write | Ownership assertion before save | `shared/authorization/services.py` |
| DB row-level | RLS policies compare row's profile key to transaction-local GUC; unset GUC ⇒ empty string ⇒ zero rows (fail-closed) | `apps/subjects/migrations/0002_enable_rls.py`, `shared/database/rls.py` |
| Tokens | A's tokens only ever authenticate as A; rotation/blacklist limits stolen-refresh reuse | SimpleJWT settings |

**Current caveat:** RLS is not *enforced* in local dev because the dev role is a PostgreSQL superuser (superusers bypass RLS). Application-layer isolation is fully active and tested. RLS enforcement must be validated with a restricted role before production.

For resources that don't exist yet (documents, revisions, embeddings, files, jobs, AI artifacts): the same two-layer pattern is the mandated design — app-layer checks plus RLS policies keyed on `profile_id`.

## Object storage & signed URLs

- Provider: `providers/storage/local.py` (local filesystem).
- URLs are HMAC-signed via Django `TimestampSigner` + a SHA-256 key digest, expiring after `SIGNED_URL_TTL_SECONDS` (300 s default).
- `verify()` rejects expired/forged tokens with `403`.
- Path-traversal guard in `delete()` (resolved path must stay under root).
- ⚠️ **Gap:** no views currently serve upload/download routes; nothing stores or fetches blobs yet.

## What is NOT implemented yet

| Control (spec §23) | Status |
|---|---|
| Rate limiting | ❌ (429 code reserved in contract) |
| File type/size validation | ❌ (arrives with ingestion) |
| CORS configuration | ❌ dev uses same-origin Vite proxy |
| CSRF | ✅ middleware enabled; JWT APIs are cookie-less so CSRF risk is minimal today |
| Security headers | 🟡 prod settings define HSTS/SSL redirect/secure cookies; dev sends none special |
| Audit logging | ❌ (`audit` app skeleton only) |
| Password-reset email flow | 🔧 stub endpoint only |
| Prompt-injection defenses / AI data minimization | ❌ n/a until AI phases |

## Secret management

- Secrets come from environment (`.env`, gitignored); `.env.example` holds placeholders only.
- `prod.py` refuses to run without `DJANGO_SECRET_KEY`.
- Signed URLs derive their signing key from the Django secret — rotating it invalidates outstanding URLs and tokens.
- Repository scanned for committed secrets: none found (only the marked dev-only fallback key).

## Error handling & sensitive data

- All errors funnel through `shared/exceptions/handlers.py` → uniform envelope; unexpected exceptions become `500 INTERNAL_ERROR` with request ID, never a traceback to the client.
- Logging never includes passwords/tokens/signed URLs/raw content; log lines carry only level, time, logger, request ID, message.
