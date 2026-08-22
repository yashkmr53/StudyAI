# API Reference — after Phase 3

Base `/api/v1` · no trailing slashes · JSON (storage PUT is raw bytes) · Bearer auth except signed storage URLs.
Authoritative contract: [`../openapi.yaml`](../openapi.yaml).

Phase 1–2 endpoints unchanged: auth, profiles, subjects, canvas ([`../phase_2/backend/API.md`](../../phase_2/backend/API.md)). This page adds documents, jobs, and storage.

---

## Documents

### POST /documents — authenticated

Request `{"profile": "<uuid>", "subject": "<uuid>"?, "source_type": "image"|"pdf", "filename": "…"}`.

Response `201`:

```json
{
  "document": {"id": "…", "source": "upload", "source_type": "image", …},
  "page": {"id": "…", "page_number": 1, "ocr_status": "pending", …},
  "upload": {"url": "/api/v1/storage/upload/<key>?token=…&sig=…", "method": "PUT", "key": "<profileId>/<pageId>.png"}
}
```

Errors: `403` foreign profile/subject; `422` validation.
Side effects: creates Document + first DocumentPage.

### GET /documents · GET /documents/{id}
Own documents list (paginated) / retrieve. Foreign → 404.

### GET /documents/{id}/pages
Pages incl. `ocr_status`, `needs_review`, `current_revision_id`, `image_ref`.

### GET /documents/{id}/revisions?page={pageId}
Revisions across the document (optionally per page), newest content included via snapshot + line_count.

### POST /documents/{id}/revisions — two modes

**Mode A — finalize upload (§46):** body `{"page_id"}` → validates stored object, hashes sha256, creates immutable revision n+1, enqueues logical OCR job. Response **202**: `{"revision": {…}, "job": {…}}`.
- Idempotent: identical content ⇒ same job id returned (§20 key).
- Errors: `422` no uploaded object; `404` foreign page/document.

**Mode B — user edit (§48):** body `{"page_id", "lines": [{"line_index": 0, "text": "…", "bbox"?]}` → creates completed revision attributed to `edited_by`, no OCR job. Response `200`. Old revisions untouched.

### POST /documents/{id}/retry-processing

Body `{"page_id"}`. Resets the current revision's failed OCR job (`FAILED_RETRYABLE`/`FAILED_DEAD_LETTER`) to QUEUED and re-dispatches → **202 `{job}`**. Succeeded jobs → `422 VALIDATION_ERROR`.

### POST /documents/pages/{page_id}/finalize-upload
Explicit §46 variant of Mode A → **202**.

## Storage (signed, self-authorizing)

### PUT /storage/upload/{key}?token=…
Validates: token signature+expiry+action+key match; Content-Type in {image/jpeg, image/png, image/webp}; size ≤ 10 MB (`UPLOAD_MAX_BYTES`). Responses: `200 {key,size}` · `403` forged/expired/mismatched · `413` oversize envelope · `422` bad type/empty.

### GET /storage/download/{key}?token=…
Streams object bytes; `403` on invalid/expired/wrong-action tokens.

Issuing download URLs is a provider call today (no public endpoint); tests exercise it directly. A signing endpoint with ownership-prefix checks is trivial to add when the frontend needs it.

## Jobs (§60)

### GET /jobs/{id} — owner-scoped via job.profile_id
`200 {"id","job_type","resource_type","resource_id","status","attempt_count","last_error","created_at"}` · foreign → 404.

### POST /jobs/{id}/cancel
QUEUED → CANCELLED (`200`); RUNNING → CANCELLING (cooperative; executor finalizes as CANCELLED if cancel observed before completion); terminal states → `422`.

---

## Job states (implemented)

```text
queued → running → succeeded | failed_retryable (next_retry_at backoff) | failed_dead_letter
failed_retryable → queued (promoted when due)   cancelled/cancelling per above
```

## Not implemented

Everything beyond the above from spec §60: notebooks, NoteSpace PDFs, enrich/tags/questions/refresh-ai, tests, chat, revision planner.
