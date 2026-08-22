# API Reference — after Phase 4

Base `/api/v1` · no trailing slashes · Bearer auth (storage URLs self-authorize).
Authoritative contract: [`../openapi.yaml`](../openapi.yaml).

Phase 1–3 endpoints unchanged: auth, profiles, subjects, canvas, documents upload/finalize/revisions/retry, jobs. See [`../phase_3/backend/API.md`](../../phase_3/backend/API.md). New in Phase 4:

---

## POST /documents/{id}/pdf — authenticated (§60)

Requests a typed-PDF artifact for the document's **current** page revisions.

| Scenario | Response |
|---|---|
| Artifact for this exact content + renderer version already exists | `200 {"digitized_document": {…}, "job": null}` |
| New/changed content | `202 {"digitized_document": null, "job": {…}}` — async render |
| Foreign/unknown document | `404` |
| Any page lacks a current revision | `422 VALIDATION_ERROR` |

Side effects: at most one render job per unique descriptor hash (`pdf:{doc}:{hash32}`); immutable artifact created on success.

```json
{ "digitized_document": {
    "id": "…", "document": "…",
    "revision_ids": [{"revision_id": "…", "page_number": 1}],
    "renderer_version": "notespace-pdf-v1",
    "file_size": 15333,
    "created_at": "…" } }
```

## GET /digitized-documents[?document={id}] — authenticated
List own artifacts, optionally filtered by document.

## GET /digitized-documents/{id} — authenticated
Artifact metadata. Foreign → 404.

## GET /digitized-documents/{id}/download — authenticated (§49/§23)

Authorization checked first; then returns a **short-lived signed URL** payload:

```json
{ "url": "/api/v1/storage/download/<key>?token=…&sig=…",
  "expires_in": 300, "file_size": 15333 }
```

Errors: `404` foreign/unknown or object missing from storage.
The signed URL itself requires no auth and expires after `SIGNED_URL_TTL_SECONDS`.

---

## Not implemented

Everything else from spec §60 beyond phases 1–4: notebooks, AI Classroom endpoints (enrich/tags/questions/refresh-ai), tests, chat, revision planner.
