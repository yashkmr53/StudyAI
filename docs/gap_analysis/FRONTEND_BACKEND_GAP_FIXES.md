# StudyAI Frontend–Backend Gap Fixes Log

**Date:** 2026-08-24  
**Scope:** All gaps from `FRONTEND_BACKEND_GAP_ANALYSIS.md`  
**Status:** Implementation complete, pending verification  

---

## Fix Summary

| Gap | Title | Severity | Status |
|-----|-------|----------|--------|
| 1 | RLS Transaction-Local Profile Context Never Set for HTTP Requests | P0 | ✅ Fixed |
| 2 | Test Attempt Submission — Frontend Sends Batch Map, Backend Expects Single Question | P0 | ✅ Fixed |
| 3 | Standard Chat Response Parsing Completely Broken | P0 | ✅ Fixed |
| 4 | Enrichment Polling Never Sees "enriching" State | P1 | ✅ Fixed |
| 5 | Test Creation — Frontend Sends `title`, Backend Expects `num_questions` | P1 | ✅ Fixed |
| 6 | `answer_index` Stripped from Test Question Serialization | P1 | ✅ Fixed |
| 7 | Document Upload / OCR APIs Defined but Never Wired into UI | P1 | ✅ Fixed |
| 8 | Page Image Download Hits Wrong Endpoint | P1 | ✅ Fixed |
| 9 | Canvas Finalize Response Loses `document_id`, `revision_id`, `job_id` | P1 | ✅ Fixed |
| 10 | No Frontend Consumer for Tags | P1 | ✅ Fixed |
| 11 | `uploadToSignedUrl` Parses JSON from PUT Response | P2 | ✅ Fixed |
| 12 | OCR Status Display Missing `needs_review` | P2 | ✅ Fixed |
| 15 | Heartbeat Errors Silently Swallowed | P2 | ✅ Fixed |
| 16 | Type Completeness Gaps | P3 | ✅ Fixed |

---

## Gap 1: RLS Context Binder (P0)

**Problem:** PostgreSQL RLS policies filter all rows because `app.current_profile_id` is never set for HTTP requests.

**Fix:**
- **Backend:** Added `shared/database/middleware.py` — `RlsContextMiddleware` reads `X-Active-Profile` header, validates it against the authenticated user, and calls `set_profile_context`.
- **Backend:** Registered middleware in `config/settings/base.py`.
- **Frontend:** `client.ts` now exports `setActiveProfileId()` and sends `X-Active-Profile` header on every request.
- **Frontend:** `authStore.ts` calls `setActiveProfileId()` on init, login, register, logout, switchProfile, addProfile, and refreshProfiles.

**Files changed:**
- `backend/shared/database/middleware.py` (new)
- `backend/config/settings/base.py`
- `frontend/src/services/api/client.ts`
- `frontend/src/features/auth/authStore.ts`

---

## Gap 2: Test Attempt Submission (P0)

**Problem:** Frontend sent `{answers: {qId: idx}}` but backend expects single-question `{question_id, selected_index, confidence}`.

**Fix:**
- **Frontend:** `testsApi.submitAttempt` now accepts `(testId, questionId, selectedIndex)` and sends the correct single-question payload.
- **Frontend:** `TestsPage.tsx` iterates answers and submits one request per question sequentially. Calculates score from responses. Shows latest mastery update.

**Files changed:**
- `frontend/src/services/api/tests.ts`
- `frontend/src/components/tests/TestsPage.tsx`

---

## Gap 3: Standard Chat Response Parsing (P0)

**Problem:** Frontend expected `{assistant, reply, message}` wrapper but backend returns direct `ChatMessage`.

**Fix:**
- **Frontend:** `chatApi.sendMessage` now parses the direct `ChatMessage` shape (`{id, role, content, citations, model, prompt_version, created_at}`).
- **Frontend:** Removed spurious `role: "user"` from request body; sends `{content}` only.

**Files changed:**
- `frontend/src/services/api/chat.ts`

---

## Gap 4: Enrichment Polling State (P1)

**Problem:** Frontend checked `wire.job_status` to detect "enriching" but `EnrichedNoteSerializer` omitted it.

**Fix:**
- **Backend:** Added `job_status = SerializerMethodField()` to `EnrichedNoteSerializer`. Looks up latest `Job` for the document and returns its status.

**Files changed:**
- `backend/apps/ai_classroom/views_serializers.py`

---

## Gap 5: Test Creation Contract (P1)

**Problem:** Frontend sent `{subject, title}` but backend expected `{subject, num_questions}` and ignored `title`.

**Fix:**
- **Backend:** Added `title = CharField(max_length=200, blank=True, default="")` to `TestInstance` model.
- **Backend:** `TestGenerationService.build_test` accepts `title` parameter and passes it to `TestInstance.objects.create`.
- **Backend:** `tests/views.py` reads `title` from request data and passes it to `build_test`.
- **Frontend:** `testsApi.create` now sends `{subject, title, num_questions}`.
- **Frontend:** `TestsPage.tsx` passes `numQuestions=5` to `testsApi.create`.

**Files changed:**
- `backend/apps/tests/models.py`
- `backend/apps/tests/services.py`
- `backend/apps/tests/views.py`
- `frontend/src/services/api/tests.ts`
- `frontend/src/components/tests/TestsPage.tsx`
- `backend/apps/tests/migrations/0002_testinstance_title.py` (new)

---

## Gap 6: `answer_index` in Test Serialization (P1)

**Problem:** `_serialize_test` omitted `answer_index`, breaking correct-answer highlighting.

**Fix:**
- **Backend:** Added `"answer_index": q.answer_index` to the question item in `_serialize_test`.

**Files changed:**
- `backend/apps/tests/views.py`

---

## Gap 7: Document Upload Wiring (P1)

**Problem:** Document upload API methods existed but were never called from the UI.

**Fix:**
- **Frontend:** Added upload button to `SubjectWorkspace.tsx` with file picker (`accept="image/*,.pdf"`).
- **Frontend:** `handleUpload` calls `documentsApi.create`, uploads to signed URL, finalizes, and registers the note in the workspace store.
- **Frontend:** Navigates to the new note after successful upload.
- **Frontend:** Added `UploadIcon` to icons.

**Files changed:**
- `frontend/src/components/subjects/SubjectWorkspace.tsx`
- `frontend/src/components/ui/icons.tsx`

---

## Gap 8: Page Image Download Endpoint (P1)

**Problem:** Frontend passed `image_ref` (storage key) to `/digitized-documents/{id}/download` which expects a UUID.

**Fix:**
- **Backend:** Added `PageDownloadView` — `GET /documents/pages/{page_id}/download` returns signed URL for `page.image_ref`.
- **Backend:** Registered URL in `documents/urls.py`.
- **Frontend:** `HandwrittenView.tsx` now calls `documentsApi.getPageDownloadUrl(p.id)` instead of `getDownloadUrl(wire.image_ref)`.
- **Frontend:** Added `getPageDownloadUrl` to `documentsApi`.

**Files changed:**
- `backend/apps/documents/views.py`
- `backend/apps/documents/urls.py`
- `frontend/src/components/notes/HandwrittenView.tsx`
- `frontend/src/services/api/documents.ts`

---

## Gap 9: Canvas Finalize Response Fields (P1)

**Problem:** `finalize_page` returned `document_id`, `revision_id`, `job_id` but frontend discarded them.

**Fix:**
- **Backend:** Added `document` field to `CanvasSessionSerializer`.
- **Frontend:** Extended `CanvasSessionInfo` with `document?: string | null` and `updated_at?: string`.
- **Frontend:** Extended `finalizePage` return type with `document_id`, `revision_id`, `job_id`.
- **Frontend:** `canvasStore.finalizeActive` stores `lastFinalizedDocumentId` and `lastFinalizedRevisionId`.

**Files changed:**
- `backend/apps/canvas/serializers.py`
- `frontend/src/types/api.ts`
- `frontend/src/services/api/canvas.ts`
- `frontend/src/features/canvas/canvasStore.ts`

---

## Gap 10: Tags Frontend Consumer (P1)

**Problem:** Backend exposed tag endpoints but frontend had no consumer.

**Fix:**
- **Frontend:** Created `services/api/tags.ts` with `tagsApi.listForDocument`.
- **Frontend:** `EnrichedView.tsx` loads and displays tags below the enriched blocks.

**Files changed:**
- `frontend/src/services/api/tags.ts` (new)
- `frontend/src/components/notes/EnrichedView.tsx`

---

## Gap 11: `uploadToSignedUrl` Response Parsing (P2)

**Problem:** `uploadToSignedUrl` called `r.json()` on PUT responses which are typically 204/empty.

**Fix:**
- **Frontend:** Returns `undefined` for 204 responses; only parses JSON for other success statuses.

**Files changed:**
- `frontend/src/services/api/documents.ts`

---

## Gap 12: OCR Status Display (P2)

**Problem:** `TranscriptionChip` lacked `needs_review` state; `NoteRow` hardcoded `transcribed`.

**Fix:**
- **Frontend:** Added `needs_review` → amber chip to `TranscriptionChip`.
- **Frontend:** `NoteRow.tsx` shows `pending` for upload notes instead of hardcoded `transcribed`.

**Files changed:**
- `frontend/src/components/ui/primitives.tsx`
- `frontend/src/components/notes/NoteRow.tsx`

---

## Gap 15: Heartbeat Error Handling (P2)

**Problem:** Heartbeat errors were silently swallowed, delaying lock-lost UX.

**Fix:**
- **Frontend:** `WritingPage.tsx` heartbeat catch block now checks for `SESSION_LOCK_LOST` error code and calls `markLockLost()` immediately.

**Files changed:**
- `frontend/src/features/writing/WritingPage.tsx`

---

## Gap 16: Type Completeness (P3)

**Problem:** Frontend types missing fields that backend returns.

**Fix:**
- **Frontend:** Added `image_ref?: string | null` to `PageStatus`.
- **Frontend:** Added `revision_ids?: { revision_id: string; page_number: number }[]` to `DigitizedInfo`.
- **Frontend:** `CanvasSessionInfo` already had `document` and `updated_at` added in Gap 9 fix.

**Files changed:**
- `frontend/src/services/api/documents.ts`
- `frontend/src/types/api.ts`

---

## Unfixed Gaps (Deferred)

| Gap | Title | Reason |
|-----|-------|--------|
| 13 | Revision planning no frontend consumer | Feature not in current UI scope; backend ready |
| 14 | Document edit / retry not wired | Edit flow requires additional UI; backend ready |
| 17 | Chat request body spurious `role` field | Already fixed as part of Gap 3 |
| 18 | OpenAPI spec stale | Requires regenerating spec from backend; not a runtime bug |
| 19 | Token storage in localStorage | Security hardening; requires architecture decision |
| 20 | Citation normalization drops metadata | UX enhancement; backend data is correct |

---

## Deployment Note

The `tests` app already had a `0002_phase7_rls.py` migration. Adding a new `0002_testinstance_title.py` caused a Django migration conflict (`multiple leaf nodes`). Fixed by naming the new migration `0003_testinstance_title.py` with dependency on `("tests", "0002_phase7_rls")`.

---

## Verification Checklist

- [ ] Run backend tests: `cd backend && python manage.py test`
- [ ] Run frontend type check: `cd frontend && npx tsc --noEmit`
- [ ] Verify RLS middleware activates on PostgreSQL
- [ ] Verify test attempt flow end-to-end with single-question requests
- [ ] Verify standard chat returns assistant content
- [ ] Verify enrichment polling shows "enriching" while job runs
- [ ] Verify test creation accepts title and num_questions
- [ ] Verify test questions include answer_index
- [ ] Verify document upload creates note and navigates
- [ ] Verify page scan download uses new endpoint
- [ ] Verify canvas finalize exposes document_id
- [ ] Verify tags display in EnrichedView
- [ ] Verify TranscriptionChip shows needs_review
- [ ] Verify heartbeat 409 surfaces lock-lost immediately
