# StudyAI Frontend–Backend Gap Analysis

**Date:** 2026-08-24  
**Scope:** Phases 1–6 implementation (PostgreSQL backend, React PWA frontend)  
**Method:** End-to-end workflow tracing, API contract inspection, permission/policy audit, test coverage review  

---

## Executive Summary

The StudyAI repository contains a sophisticated Django + React architecture with defense-in-depth authorization, immutable revisions, and an AI enrichment pipeline. However, the **frontend and backend have diverged significantly** in several critical areas. The most severe issue is a **missing request-scoped RLS context binder** that will cause the entire API to return empty data in production (PostgreSQL). Beyond that, the test attempt flow, standard chat, enrichment polling, and document upload flows are all broken due to frontend/backend contract mismatches. Several backend endpoints have no frontend consumer at all.

---

## Critical Gaps

### Gap 1: RLS Transaction-Local Profile Context Never Set for HTTP Requests

**Classification:** BACKEND BUG  
**Severity:** P0 — Critical  
**Expected behavior:** Every HTTP request should have `app.current_profile_id` bound transaction-locally so PostgreSQL RLS policies can scope data to the active profile.  
**Actual behavior:** The GUC is only set inside Celery workers (`jobs/services.py:123`). No middleware, DRF dispatch hook, or view decorator sets it for normal API requests. On PostgreSQL, RLS policies using `current_setting('app.current_profile_id', true)` evaluate to `NULL` for all rows, so the USING clause filters everything out.  
**Frontend path:** `authStore.init()` → `profilesApi.list()` → empty array because RLS blocks all subjects/documents.  
**Backend path:** `config/settings/base.py:57-69` (MIDDLEWARE) → no RLS middleware. `shared/database/rls.py:16-22` (`set_profile_context`) exists but is never called from request handling. `apps/jobs/services.py:119-124` is the only caller.  
**Root cause:** The architecture document (§3) specifies "defense in depth" with RLS, but the request-scoped mechanism to bind the active profile was never implemented.  
**Evidence:**
- `backend/shared/database/rls.py:16-22` — `set_profile_context` function exists
- `backend/config/settings/base.py:57-69` — MIDDLEWARE has no RLS component
- `backend/apps/jobs/services.py:119-124` — only Celery workers call `profile_scoped_transaction`
- `grep` for `set_profile_context` / `profile_scoped_transaction` across `backend/` returns only these locations  
**Recommended fix:** Add a DRF request hook or middleware that sets `app.current_profile_id` from a trusted source (e.g., a backend-resolved active profile from the JWT or a request header). This is the single largest production blocker.  
**Test coverage:** `backend/tests/unit/test_shared.py:20-44` tests the RLS helper in isolation, but no integration test verifies that HTTP requests actually set the context. CI uses SQLite where RLS is a no-op, so this regression is untested.

---

### Gap 2: Test Attempt Submission — Frontend Sends Batch Map, Backend Expects Single Question

**Classification:** FRONTEND BUG + BACKEND BUG (contract mismatch)  
**Severity:** P0 — Critical  
**Expected behavior:** Frontend submits test answers; backend records each attempt, updates mastery, and returns the result.  
**Actual behavior:** Frontend sends `{"answers": {"questionId": selectedIndex, ...}}` (`frontend/src/services/api/tests.ts:86-93`). Backend `AttemptInSerializer` expects `{"question_id": UUID, "selected_index": int, "confidence": float}` for a **single** question (`backend/apps/tests/views.py:16-19`). The backend rejects the payload with validation errors. The frontend has a local-grading fallback (`TestsPage.tsx:167-172`), so the UI doesn't crash, but **server-side mastery scoring never runs**.  
**Frontend path:** `TestsPage.tsx:161-173` → `testsApi.submitAttempt()` → `POST /tests/{id}/attempts` with `{answers}` → catch block does local grading.  
**Backend path:** `tests/views.py:91-140` → `AttemptInSerializer` validates `question_id` + `selected_index` + `confidence` → 422 on frontend payload.  
**Root cause:** The frontend API client was written assuming a batch submission endpoint that doesn't exist. The backend implements one-question-at-a-time with idempotency (`IdempotencyConflict` on re-attempt).  
**Evidence:**
- `backend/apps/tests/views.py:16-19` — single-question serializer
- `backend/apps/tests/views.py:91-140` — single-attempt action
- `frontend/src/services/api/tests.ts:86-93` — sends `{answers: Record<string, number>}`
- `frontend/src/components/tests/TestsPage.tsx:161-173` — local fallback grading
- `backend/tests/api/test_learning_features.py:141-171` — tests send `{"question_id": ..., "selected_index": ..., "confidence": ...}`  
**Recommended fix:** Either change backend to accept a batch `{"answers": [...]}` or change frontend to send one request per question. The backend approach is more aligned with the idempotency design.  
**Test coverage:** Backend API tests cover single-question submission correctly. Frontend has zero API integration tests.

---

### Gap 3: Standard Chat Response Parsing Completely Broken

**Classification:** FRONTEND BUG  
**Severity:** P0 — Critical  
**Expected behavior:** User sends a message in standard chat mode; backend returns the assistant reply; frontend displays it.  
**Actual behavior:** Backend `messages` action returns a **direct `ChatMessage` object**: `{"id", "role", "content", "citations", "model", "prompt_version", "created_at"}` (`backend/apps/chat/views.py:72-78`). Frontend `sendMessage` looks for `payload.assistant`, `payload.reply`, or `payload.message` (`frontend/src/services/api/chat.ts:88-105`). None of these keys exist in the direct message object. Result: `assistantContent = ""` and `citations = []`; the assistant bubble is always empty in standard mode.  
**Frontend path:** `ChatPage.tsx:113` → `chatApi.sendMessage()` → checks `rec.assistant ?? rec.reply ?? rec.message` → always `undefined` → empty assistant bubble.  
**Backend path:** `chat/views.py:72-78` → returns `ChatMessageSerializer(message).data` directly.  
**Root cause:** The frontend was written expecting a wrapped exchange format (possibly from an earlier API design or from the agent endpoint shape). The standard chat endpoint was never updated to match, or the frontend was never updated.  
**Evidence:**
- `backend/apps/chat/views.py:72-78` — returns `ChatMessageSerializer(message).data`
- `frontend/src/services/api/chat.ts:88-105` — looks for `assistant`/`reply`/`message` keys
- `backend/tests/api/test_learning_features.py:189-200` — backend test asserts `message["content"]` and `message["citations"]` directly
- `frontend/src/components/chat/ChatPage.tsx:113-118` — standard mode replaces pending message with empty reply  
**Recommended fix:** Update `frontend/src/services/api/chat.ts:88-105` to parse the direct `ChatMessage` shape: `{id, role, content, citations, model, prompt_version, created_at}`.  
**Test coverage:** Backend tests verify the response shape. Frontend has zero integration tests for chat.

---

### Gap 4: Enrichment Polling Never Sees "enriching" State

**Classification:** FRONTEND BUG + BACKEND BUG (contract mismatch)  
**Severity:** P1 — High  
**Expected behavior:** While enrichment is running, frontend shows a progress state.  
**Actual behavior:** `snapshotFromWire` checks `wire.job_status` to decide `"enriching"` (`frontend/src/services/api/enrichment.ts:50`), but `EnrichedNoteSerializer` does not include `job_status` (`backend/apps/ai_classroom/views_serializers.py:12-16`). While a job runs, the frontend either sees the old note as `"enriched"` or gets a 404, never `"enriching"`.  
**Frontend path:** `EnrichedView.tsx:62-76` polls only when `snapshot.state === "enriching"`, but that state is never reached.  
**Backend path:** `ai_classroom/views_serializers.py:12-16` — `job_status` not in serializer fields.  
**Root cause:** The serializer was designed without `job_status`, but the frontend depends on it for polling state.  
**Evidence:**
- `backend/apps/ai_classroom/views_serializers.py:12-16` — no `job_status`
- `frontend/src/services/api/enrichment.ts:35,50` — `WireEnrichment` declares `job_status?`, `snapshotFromWire` uses it
- `frontend/src/components/notes/EnrichedView.tsx:62` — polls only on `"enriching"`  
**Recommended fix:** Either add `job_status` to `EnrichedNoteSerializer` or have `GET /documents/{id}/enrichment` return a separate job status indicator.  
**Test coverage:** Backend tests for enrichment don't verify `job_status` in the enrichment endpoint response.

---

### Gap 5: Test Creation — Frontend Sends `title`, Backend Expects `num_questions`

**Classification:** FRONTEND BUG + BACKEND BUG (contract mismatch)  
**Severity:** P1 — High  
**Expected behavior:** Frontend creates a test with a title; backend creates it with the requested number of questions.  
**Actual behavior:** Frontend sends `{subject, title}` (`frontend/src/services/api/tests.ts:64`). Backend reads `request.data.get("subject")` and `request.data.get("num_questions", 5)` (`backend/apps/tests/views.py:62-75`). Backend ignores `title` entirely (no `title` field on `TestInstance` — `tests/models.py:11-21`). Frontend `normalizeTest` maps `wire.title` to `test.title` (`tests.ts:41`), which always becomes `"Untitled test"`.  
**Frontend path:** `TestsPage.tsx:49-52` → `testsApi.create(subjectId, title)` → sends `{subject, title}`.  
**Backend path:** `tests/views.py:60-80` → reads `num_questions` (defaults to 5), ignores `title`.  
**Root cause:** The frontend and backend were built against different API contracts.  
**Evidence:**
- `backend/apps/tests/views.py:62-75` — expects `num_questions`, no `title` field
- `backend/apps/tests/models.py:11-21` — no `title` field
- `frontend/src/services/api/tests.ts:61-69` — sends `{subject, title}`
- `frontend/src/components/tests/TestsPage.tsx:49-52` — passes localized title  
**Recommended fix:** Backend: add `title` field to `TestInstance` and accept it in create. Frontend: send `num_questions` (default 5 or make it configurable).  
**Test coverage:** Backend tests send `{"num_questions": 3}` correctly.

---

### Gap 6: `answer_index` Stripped from Test Question Serialization

**Classification:** BACKEND BUG  
**Severity:** P1 — High  
**Expected behavior:** Frontend can display the correct answer after test submission.  
**Actual behavior:** `_serialize_test` (`backend/apps/tests/views.py:36-44`) returns `id`, `difficulty`, `prompt`, `options`, `answered`, `selected_index`, `correct` but **not** `answer_index`. Frontend expects `answerIndex` to highlight correct answers (`TestsPage.tsx:241,268`). Without it, `q.answerIndex` is always `null`, so correct-answer highlighting is broken.  
**Frontend path:** `TestsPage.tsx:241` — `q.answerIndex === oi` never true → no green highlight for correct answer.  
**Backend path:** `tests/views.py:36-44` — `answer_index` omitted from serialized question item.  
**Root cause:** The serializer was designed without `answer_index`, likely to avoid leaking answers before submission. But it's needed for post-submission review.  
**Evidence:**
- `backend/apps/tests/views.py:36-44` — no `answer_index`
- `frontend/src/services/api/tests.ts:81-83` — expects `answer_index`
- `frontend/src/components/tests/TestsPage.tsx:241,268` — uses `q.answerIndex`  
**Recommended fix:** Include `answer_index` in `_serialize_test` when `include_questions=True` and the user has already submitted (or always, since it's needed for review mode).  
**Test coverage:** Backend tests don't assert `answer_index` presence in serialized output.

---

### Gap 7: Document Upload / OCR APIs Defined but Never Wired into UI

**Classification:** FRONTEND BUG  
**Severity:** P1 — High  
**Expected behavior:** Users can upload documents (images/PDFs), trigger OCR, and view transcriptions.  
**Actual behavior:** `documentsApi.create`, `uploadToSignedUrl`, `finalizeUpload`, `submitEdit`, and `retryProcessing` are defined in `frontend/src/services/api/documents.ts:59-103` but have **zero call sites** outside their definition file. The only `documentsApi` usages are read-only in `HandwrittenView.tsx:270-285`. The entire document-upload and OCR-trigger UI is disconnected.  
**Frontend path:** `HandwrittenView.tsx` — read-only calls to `pages()` and `revisions()`. No upload or edit paths wired.  
**Backend path:** `backend/apps/documents/views.py:56-89, 106-128, 130-151` — endpoints fully implemented and tested.  
**Root cause:** The frontend document-upload flow was likely planned but never connected.  
**Evidence:**
- `frontend/src/services/api/documents.ts:59-103` — methods defined but unused
- `grep` for `documentsApi.create`, `documentsApi.uploadToSignedUrl`, `documentsApi.finalizeUpload`, `documentsApi.submitEdit`, `documentsApi.retryProcessing` across `frontend/src/` returns only the definition file  
**Recommended fix:** Wire the upload flow into the UI (e.g., `HandwrittenView` or a new upload dialog).  
**Test coverage:** Backend API tests cover the full upload/OCR flow end-to-end.

---

### Gap 8: Page Image Download Hits Wrong Endpoint

**Classification:** FRONTEND BUG  
**Severity:** P1 — High  
**Expected behavior:** Uploaded page scans are displayed via signed download URLs.  
**Actual behavior:** `HandwrittenView.tsx:277` calls `documentsApi.getDownloadUrl(wire.image_ref)`. `image_ref` is an object-storage key (e.g. `"<profile>/<page>.png"`), but the backend route `GET /digitized-documents/{id}/download` (`backend/apps/documents/urls.py:31`) expects a `DigitizedDocument` UUID. The call will 404. There is no backend endpoint that turns `image_ref` into a signed URL.  
**Frontend path:** `HandwrittenView.tsx:274-281` → passes storage key to `/digitized-documents/{id}/download`.  
**Backend path:** `backend/apps/documents/views.py:276-287` — expects `DigitizedDocument` PK, looks up artifact by ID.  
**Root cause:** The frontend confuses `image_ref` (storage key for page scans) with `DigitizedDocument` ID (for PDF artifacts). These are different resources with different download endpoints.  
**Evidence:**
- `backend/apps/documents/views.py:276-287` — `DigitizedDownloadView` takes `pk`, calls `NoteSpaceService.get_owned_artifact(request.user, str(pk))`
- `frontend/src/components/notes/HandwrittenView.tsx:277` — passes `wire.image_ref` (storage key)
- `frontend/src/services/api/documents.ts:119-123` — `getDownloadUrl` hits `/digitized-documents/${digitizedId}/download`  
**Recommended fix:** Add a backend endpoint like `GET /documents/pages/{page_id}/download` that returns a signed URL for `page.image_ref`, or expose a serializer method on `DocumentPageSerializer`.  
**Test coverage:** No frontend test covers this path.

---

### Gap 9: Canvas Finalize Response Loses `document_id`, `revision_id`, `job_id`

**Classification:** FRONTEND + BACKEND MISMATCH  
**Severity:** P1 — High  
**Expected behavior:** After finalizing a canvas page, the frontend knows the created `Document` ID and can link the note.  
**Actual behavior:** `CanvasSyncService.finalize_page` returns `{page_id, is_finalized, already_finalized, document_id, revision_id, job_id}` (`backend/apps/canvas/services.py:221-228`). Frontend `canvasApi.finalizePage` return type only includes `{page_id, is_finalized, already_finalized}` (`frontend/src/services/api/canvas.ts:59`), and `canvasStore.finalizeActive` discards `document_id`, `revision_id`, `job_id` (`frontend/src/features/canvas/canvasStore.ts:96-108`). Additionally, `CanvasSessionSerializer` does not include the `document` field (`backend/apps/canvas/serializers.py:19-23`), and `CanvasSessionInfo` lacks it (`frontend/src/types/api.ts:65-75`).  
**Frontend path:** `WritingPage.tsx:460` → `finalizeActive()` → response truncated → `document_id` lost → cannot link canvas note to document.  
**Backend path:** `canvas/services.py:221-228` — returns full payload; `canvas/serializers.py:19-23` — omits `document`.  
**Root cause:** The serializer was not updated when `finalize_page` started returning `document_id`/`revision_id`/`job_id`. The frontend type was never extended either.  
**Evidence:**
- `backend/apps/canvas/services.py:221-228` — returns `document_id`, `revision_id`, `job_id`
- `backend/apps/canvas/serializers.py:19-23` — `CanvasSessionSerializer` fields omit `document`
- `frontend/src/services/api/canvas.ts:59` — `FinalizeResponse` omits extra fields
- `frontend/src/features/canvas/canvasStore.ts:96-108` — discards extra fields
- `frontend/src/types/api.ts:65-75` — `CanvasSessionInfo` lacks `document`  
**Recommended fix:** Add `document` to `CanvasSessionSerializer` and extend `FinalizeResponse` type. Frontend should store the `document_id` to link the note.  
**Test coverage:** Backend tests for canvas finalize check the service return but not the API response shape.

---

### Gap 10: No Frontend Consumer for Tags

**Classification:** FRONTEND BUG  
**Severity:** P1 — High  
**Expected behavior:** Users can view and manage tags linked to documents and subjects.  
**Actual behavior:** Backend exposes `/api/v1/tags` (full `TagSerializer`) and `/documents/{id}/tags` (simplified shape). The frontend has **zero tag-related components and zero API calls** for tags. `Tag.rename` endpoint is also unused.  
**Frontend path:** No files exist under `frontend/src/` for tags.  
**Backend path:** `ai_classroom/views.py:17-58`, `documents/views.py:203-218` — fully implemented.  
**Root cause:** Tag UI was not built in the current frontend phase.  
**Evidence:**
- `backend/apps/ai_classroom/views.py:17-58` — tag list/retrieve/rename endpoints
- `frontend/src/` — no `tags.ts`, no tag components
- `grep -r "tag" frontend/src/components/` returns only unrelated matches  
**Recommended fix:** Build tag listing UI or document tags as a future phase item.  
**Test coverage:** Backend tests cover tag stability and rename.

---

## Frontend–Backend Mismatch Matrix

| # | Feature | Expected | Frontend | Backend | Gap | Severity | Root Cause |
|---|---------|----------|----------|---------|-----|----------|------------|
| 1 | RLS / Profile scoping | All requests scoped to active profile via DB RLS | Sends profile in create bodies + subjects `?profile=` | RLS GUC never set for HTTP requests; only Celery workers set it | **MISMATCH** | P0 | Missing request-scoped RLS context binder |
| 2 | Test attempts | Submit batch answers → server records attempts + updates mastery | Sends `{answers: {qId: idx}}` | Expects `{question_id, selected_index, confidence}` per question | **MISMATCH** | P0 | Frontend assumes batch endpoint; backend is single-question |
| 3 | Chat (standard mode) | Send message → get assistant reply → display | Expects `{assistant, reply, message}` wrapper | Returns direct `ChatMessage` object | **FRONTEND BUG** | P0 | Frontend written for wrong response shape |
| 4 | Enrichment polling | Show "generating" while job runs | Checks `wire.job_status` | `EnrichedNoteSerializer` omits `job_status` | **MISMATCH** | P1 | Serializer incomplete; frontend depends on missing field |
| 5 | Test creation | Create test with title + num_questions | Sends `{subject, title}` | Expects `{subject, num_questions}`; ignores `title` | **MISMATCH** | P1 | Divergent API contracts |
| 6 | Test questions | Show correct answer after submission | Expects `answer_index` in question | `_serialize_test` omits `answer_index` | **BACKEND BUG** | P1 | Serializer hides answer index |
| 7 | Document upload | Upload image/PDF → trigger OCR → view transcription | API methods defined but never called in UI | Endpoints fully implemented | **FRONTEND BUG** | P1 | Upload flow never wired into UI |
| 8 | Page image download | Display uploaded page scans | Passes `image_ref` (storage key) to `/digitized-documents/{id}/download` | Expects `DigitizedDocument` UUID | **FRONTEND BUG** | P1 | Confuses storage key with artifact ID |
| 9 | Canvas finalize | Learn created Document ID after finalization | Discards `document_id`, `revision_id`, `job_id` | Returns full payload; `CanvasSessionSerializer` omits `document` | **MISMATCH** | P1 | Serializer + frontend type incomplete |
| 10 | Tags | View/manage document/subject tags | No tag UI or API client | Fully implemented backend | **FRONTEND BUG** | P1 | Tag UI not built |
| 11 | `uploadToSignedUrl` | Upload file to signed URL | Parses JSON from PUT response | Signed URL PUT typically returns 204/empty body | **FRONTEND BUG** | P2 | Incorrect response parsing |
| 12 | OCR status display | Show accurate transcription status | `TranscriptionChip` lacks `needs_review` state; `NoteRow` hardcodes `transcribed` | Backend has `needs_review` OCR status | **FRONTEND BUG** | P2 | UI doesn't handle all OCR states |
| 13 | Revision planning | View revision overview, goals, plans | No frontend client or UI | Endpoints implemented | **FRONTEND BUG** | P2 | Feature not wired into UI |
| 14 | Document edit / retry | Edit OCR transcription or retry failed jobs | `submitEdit`, `retryProcessing` never called; no refetch after mutations | Endpoints implemented | **FRONTEND BUG** | P2 | Edit/retry flow not wired; no state refresh |
| 15 | Heartbeat errors | Surface lock-lost immediately | Swallows all heartbeat errors silently | Returns `SESSION_LOCK_LOST` on 409 | **FRONTEND BUG** | P2 | Error handling too broad |
| 16 | Type completeness | Frontend types match backend response shapes | `PageStatus` missing `image_ref`; `DigitizedInfo` missing `revision_ids`; `CanvasSessionInfo` missing `updated_at` | Backend returns these fields | **FRONTEND BUG** | P3 | Types not kept in sync |
| 17 | Chat request body | `{content}` | Sends `{role: "user", content}` | Accepts only `{content}` | **FRONTEND BUG** | P3 | Spurious field in request |
| 18 | OpenAPI spec | Matches actual backend | Stale: tests/attempts, chat/messages, revision endpoints marked "No response body" | Backend returns structured data | **MISMATCH** | P3 | Spec not regenerated after backend changes |
| 19 | Token storage | Secure session management | Plaintext in `localStorage` | Standard JWT with refresh rotation | **FRONTEND BUG** | P3 | XSS exposure risk |
| 20 | Citation normalization | Preserve full citation metadata | Reduces to `{page}` only, drops `verification_status`, `chunk_id`, `bbox` | Backend returns full `source_refs` with verification | **FRONTEND BUG** | P3 | Over-aggressive normalization |

---

## Uncertain / Needs Product Clarification

1. **`image_ref` download path:** Should there be a dedicated endpoint for page scan downloads, or should the frontend use a different mechanism? The architecture mentions private object storage with signed URLs but doesn't specify the exact page-scan download flow.

2. **Batch test submission:** Was the backend intentionally designed for single-question attempts (with idempotency) or was a batch endpoint planned? The architecture (§55–56) mentions "TestAttempt" per question, suggesting single-question is intentional, but the frontend clearly expected batch.

3. **Chat response shape:** Was the standard chat endpoint intended to return a wrapped `{user, assistant}` exchange (like the agent endpoint) or a direct message? The current backend returns a direct message, but the frontend expects wrapping.

4. **`answer_index` in test serialization:** Should `answer_index` always be present (for review mode) or only after submission? The backend currently omits it entirely.

5. **Document upload UI:** Is the document upload flow intentionally deferred to a future phase, or was it accidentally left unwired?

---

## Recommended Fix Order

| Priority | Gap | Reason |
|----------|-----|--------|
| **1st** | Gap 1 — RLS context binder | P0 production blocker; entire API returns empty on PostgreSQL |
| **2nd** | Gap 2 — Test attempt submission | P0; server-side mastery is completely bypassed |
| **3rd** | Gap 3 — Standard chat parsing | P0; core chat feature is broken for all standard-mode users |
| **4th** | Gap 4 — Enrichment polling | P1; enrichment UI is stuck in wrong state |
| **5th** | Gap 5 — Test creation contract | P1; tests are created with wrong defaults |
| **6th** | Gap 6 — `answer_index` in tests | P1; test review UI is broken |
| **7th** | Gap 7 — Document upload wiring | P1; core document feature unreachable from UI |
| **8th** | Gap 8 — Page image download | P1; uploaded scans cannot be viewed |
| **9th** | Gap 9 — Canvas finalize response | P1; canvas notes cannot be linked to documents |
| **10th** | Gap 10 — Tags UI | P1; backend feature has no consumer |
| **11th** | Gaps 11–20 | P2/P3 fixes for state management, type safety, and polish |

---

## Test Coverage Gaps

- **Zero frontend API integration tests.** None of the 4 existing frontend tests validate API contracts.
- **No PostgreSQL-backed integration tests.** CI runs on SQLite where RLS is a no-op, so Gap 1 is never caught.
- **Backend tests encode correct behavior** but don't verify response shapes match what the frontend expects (e.g., `_serialize_test` doesn't assert `answer_index` presence; chat tests assert direct `ChatMessage` shape that frontend doesn't parse).
- **OpenAPI spec is stale** and not used for contract testing.
