# API Reference (implemented endpoints only)

Base: `/api/v1` · No trailing slashes · JSON only.
Authoritative machine contract: [`../openapi.yaml`](../openapi.yaml) (regenerate: `cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py spectacular --file ../docs/phase_1/openapi.yaml`).

Common error envelope (§61):

```json
{ "error": { "code": "…", "message": "…", "request_id": "req_…", "details": {} } }
```

Codes: `INVALID_REQUEST` 400 · `UNAUTHENTICATED` 401 · `FORBIDDEN` 403 · `RESOURCE_NOT_FOUND` 404 · `REVISION_CONFLICT` 409 · `VALIDATION_ERROR` 422 · `RATE_LIMITED` 429 · `INTERNAL_ERROR` 500.

Pagination (list endpoints): page-number, size 50 → `{count, next, previous, results}`.

---

## POST /api/v1/auth/register

| | |
|---|---|
| Auth | none |
| Authorization | n/a |
| Request | `{"email": string, "password": string (min 10)}` |
| Validation | email format+unique; password ≥10 chars |
| Success | `201` → `{"user": {id,email,date_joined}, "profile": {id,name,…}, "access", "refresh"}` |
| Errors | `422` invalid/duplicate email, short password |
| Idempotency | none — duplicate email is a validation error |
| Side effects | creates User + Profile `"Default"` in one transaction |

```bash
curl -X POST :8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"a@b.dev","password":"s3curePass!x"}'
```

## POST /api/v1/auth/login

| | |
|---|---|
| Auth | none |
| Request | `{"email","password"}` |
| Success | `200 {"access","refresh"}` |
| Errors | `401 UNAUTHENTICATED` on bad credentials; `422` missing fields |
| Side effects | updates `last_login`; adds outstanding token row |

## POST /api/v1/auth/refresh

| | |
|---|---|
| Auth | none (refresh token in body) |
| Request | `{"refresh": "<jwt>"}` |
| Success | `200 {"access", "refresh"}` — rotation on: new refresh issued, old blacklisted |
| Errors | `401` invalid/blacklisted/expired token |
| Idempotency | **not idempotent by design** — replaying a rotated token fails |

## POST /api/v1/auth/logout

| | |
|---|---|
| Auth | Bearer access token required |
| Request | `{"refresh": "<jwt>"}` |
| Success | `204` empty |
| Errors | `422` missing/invalid refresh; `401` no/invalid access token |
| Side effects | refresh token blacklisted |

## POST /api/v1/auth/password-reset

| | |
|---|---|
| Auth | none |
| Request | `{"email"}` |
| Success | always `202 {"detail": "If the address exists, …"}` |
| Notes | 🔧 stub — no email sent, no reset token flow yet |

---

## /api/v1/profiles

All require Bearer auth. Ownership enforced by queryset (`user=request.user`) and object lookup.

### GET /profiles
List own profiles. `200` paginated. Query params: `page`.

### POST /profiles
`{"name": "Sem 1"}` → `201 Profile`. `422` if name missing/blank or duplicate for user.

### GET /profiles/{id}
`200` own profile; foreign/unknown → `404 RESOURCE_NOT_FOUND` (envelope).

### PATCH /profiles/{id}
Partial update `{"name": "Renamed"}` → `200`. Duplicate name → `422`.

### DELETE /profiles/{id}
`204`. Cascades to subjects (FK CASCADE). Foreign profile → `404`.

> Note: spec §60 lists DELETE for profiles; kept as implemented.

## /api/v1/subjects

### GET /subjects
List subjects across the caller's profiles. `200` paginated.

### POST /subjects
`{"profile": "<uuid>", "name": "Algorithms"}` → `201`.
Errors: unknown profile → `422`; profile owned by someone else → `403 FORBIDDEN`; duplicate `(profile,name)` → `422`.

### GET /subjects/{id}
Own subject → `200`; else `404`.

### PATCH /subjects/{id}
Rename → `200`. DELETE intentionally disabled (`http_method_names`).

---

## Auxiliary endpoints

| Path | Purpose |
|---|---|
| `/admin/` | Django admin (session auth, staff only) |
| `/api/schema/` | OpenAPI 3 YAML (drf-spectacular) |
| `/api/docs/` | Swagger UI |

## Not implemented (do not assume)

Everything in spec §60 beyond the above: notebooks, canvas, documents, revisions, PDFs, enrich/tags/questions/refresh-ai, tests, chat, revision, jobs endpoints. The storage provider *generates* signed URLs of the form `/api/v1/storage/{action}/{key}?token=…&sig=…`, but **no view serves them yet**.
