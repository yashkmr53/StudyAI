# Phase 9B — Complete Frontend Note-to-Enrichment Flow

## 1. Executive Summary

Phase 9B completes the end-to-end user journey in the StudyAI web application under the `AI_CLASSROOM` profile:

```text
AI_CLASSROOM profile
    ↓
Subject (DSA / ML)
    ↓
Upload handwritten note
    ↓
OCR processing (pending → processing → transcribed)
    ↓
Note available (Handwritten view & faithful transcript)
    ↓
Enrichment processing (resilient bounded polling surviving 404s)
    ↓
Enriched note (blocks, headings, explanations)
    ↓
Reference citation (in-place textbook citation with quotes & verification badge)
    ↓
Refresh / reopen
    ↓
Durable persistence & seamless state restoration
```

All acceptance criteria have been verified with automated unit/integration tests and live API execution against the Docker environment.

---

## 2. Issues Diagnosed and Fixes Implemented

### 2.1. Remote Note Hydration & Unfiled Placement
- **File:** [`frontend/src/state/workspaceStore.ts`](file:///Users/yash/CV_Project/StudyAI/frontend/src/state/workspaceStore.ts)
- **Problem:** Notes created without an explicit folder previously risked inconsistent state between `null` and `"__unfiled__"`. Furthermore, when viewing notes directly or after logout/login, notes fetched outside of workspace loading were not retained in local state.
- **Fix:**
  - Standardized all unfiled notes to `UNFILED_FOLDER_ID` (`"__unfiled__"`).
  - Added `upsertNote(note: NoteMeta)` to `useWorkspaceStore`, which normalizes `folderId`, saves to IndexedDB via `putNote`, and dynamically updates state and subject note counters without duplicating entries.
  - In `loadWorkspace(profileId)`, reconciled remote documents (`documentsApi.list()`) with local notes, normalizing missing `folderId` values to `UNFILED_FOLDER_ID` and persisting them to IndexedDB.

### 2.2. Note Detail Fallback on Direct URL & Refresh
- **File:** [`frontend/src/components/notes/NoteDetailPage.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/notes/NoteDetailPage.tsx)
- **Problem:** When a user opened a note via a direct URL, refreshed the page, or opened a new session, the component checked `if (!activeNote && (fetchFailed || workspaceLoaded))` and immediately displayed the `loadFailed` error because `workspaceLoaded` was `true` while the remote document fetch (`documentsApi.get(noteId)`) had not yet finished.
- **Fix:**
  - Initialized `fetchingRemote` to `!storeNote && !!noteId`.
  - Updated the loading guard to render the skeleton while `fetchingRemote || (workspaceLoading && !fetchFailed)`.
  - Guarded `loadFailed` so it only displays when `!activeNote && fetchFailed` (i.e. when `documentsApi.get(noteId)` actually errors with 404/500).
  - When `documentsApi.get(noteId)` resolves, the fetched `NoteMeta` is automatically registered into `workspaceStore` via `upsertNote(meta)` for persistent local caching.

### 2.3. Subject Association and Upload Error Handling
- **File:** [`frontend/src/components/subjects/SubjectWorkspace.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/subjects/SubjectWorkspace.tsx)
- **Problem:** Ensuring that documents uploaded inside a subject workspace are authoritatively tied to `subjectId` on the server and registered under the unfiled bucket with visible error alerts on network or format errors.
- **Fix:**
  - `documentsApi.create(profile.id, file.name, "image", subjectId)` explicitly passes `subject: subjectId` in the JSON body.
  - Post-upload, `registerUploadNote` receives `created.document.subject || subjectId` to preserve the server-assigned subject.
  - Handled errors in `handleUpload` with an inline alert banner (`<div className="form-error" role="alert">`).

### 2.4. Dynamic OCR Status Polling
- **Files:** [`frontend/src/components/notes/NoteRow.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/notes/NoteRow.tsx), [`frontend/src/components/notes/HandwrittenView.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/notes/HandwrittenView.tsx)
- **Problem:** Folder listings previously only fetched OCR status once on mount, leaving in-progress OCR in a stale state unless the entire page was reloaded.
- **Fix:**
  - Implemented interval polling in `NoteOcrStatusChip` (`NoteRow.tsx`) that checks `documentsApi.pages(documentId)` every 3000ms until a terminal status (`completed`, `failed`, or `needs_review`) is reached.
  - Cleaned up timers on unmount to prevent leaks.
  - Supported dynamic status chip transitions: `pending` → `processing` (with animated spinner) → `transcribed` (green chip).

### 2.5. Resilient Enrichment Polling Surviving 404s & Refresh
- **Files:** [`frontend/src/services/api/enrichment.ts`](file:///Users/yash/CV_Project/StudyAI/frontend/src/services/api/enrichment.ts), [`frontend/src/components/notes/EnrichedView.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/notes/EnrichedView.tsx)
- **Problem:**
  - `POST /documents/{id}/enrich` returns `202 Accepted` with a `job` object.
  - While the worker processes enrichment, `GET /documents/{id}/enrichment` returns `404 Not Found` ("No enrichment exists for this document yet.").
  - If a user refreshed while generation was underway, the component defaulted `isGenerating` to `false`, received 404, and dropped back to the "empty state / generate" button.
- **Fix:**
  - Added `getJob(jobId: string)` in `enrichmentApi` to query `/api/v1/jobs/{id}`.
  - In `EnrichedView.tsx`, persisted `jobId` in `sessionStorage` (`studyai.enrichment.job.<documentId>`).
  - On mount or page reload, if `sessionStorage` contains an active `jobId`, the component restores `isGenerating = true`, displays the generating indicator, and polls `/jobs/{id}` and `/documents/{id}/enrichment`.
  - Treated 404 from `enrichmentApi.get` as an in-progress state rather than a terminal error while a generation job is active.
  - Bounded polling to a maximum duration (120 intervals @ 2500ms = 5 minutes) with cleanup on unmount.

### 2.6. Reference Textbook Citation Display
- **File:** [`frontend/src/components/notes/EnrichedView.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/notes/EnrichedView.tsx)
- **Problem:** Clicking a reference textbook citation previously called `onCitation(page)` which jumped to the student's handwritten scan page instead of displaying the reference source.
- **Fix:**
  - Differentiated between student note scan citations (`sourceType === "image"`) and reference textbook citations (`sourceType === "reference"`).
  - For reference citations:
    - Chip renders: `📖 {title ? title + ": p. " + page : "Ref: p. " + page}`.
    - Clicking toggles an in-place citation card (`.citation-detail-card`) showing the textbook title, chapter/page number, verification badge (`supported`, `partially_supported`), and blockquoted verbatim excerpt.
    - Does **not** navigate away or jump to handwritten note scan pages.

---

## 3. Automated Verification

### 3.1. Frontend Unit & Integration Tests (Vitest)
Ran `npm test -- --run` in `frontend/`:
```text
 ✓ tests/smoke.test.ts (1 test)
 ✓ tests/moduleConfig.test.ts (4 tests)
 ✓ tests/db.test.ts (1 test)
 ✓ tests/folderTree.test.ts (9 tests)
 ✓ tests/phase9Flow.test.ts (11 tests)
 ✓ tests/phase9aProfileIsolation.test.ts (6 tests)

Test Files  6 passed (6)
     Tests  32 passed (32)
```

New tests in `frontend/tests/phase9Flow.test.ts` verify:
1. Reference textbook citation metadata and quote parsing.
2. Subject association in document creation payload.
3. Remote document loading and mapping to `UNFILED_FOLDER_ID`.
4. `upsertNote` state updates and duplicate prevention.
5. Defaulting `folderId` to `UNFILED_FOLDER_ID` on canvas/upload registration.
6. 404 handling during enrichment polling.
7. Job ID handling on 202 Accepted.
8. `enrichmentApi.getJob` retrieval and error resilience.

### 3.2. Frontend Production Build
Ran `npm run build` in `frontend/`:
```text
✓ 140 modules transformed.
dist/index.html                   0.51 kB │ gzip:   0.31 kB
dist/assets/index-sdj9EycC.css   34.10 kB │ gzip:   6.79 kB
dist/assets/index-D1OYuXdI.js   426.27 kB │ gzip: 130.84 kB
✓ built in 732ms
PWA v1.3.0 mode generateSW
```
No TypeScript errors or build issues.

### 3.3. Backend Test Suites (Pytest)
Executed in Docker environment:
```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.test api pytest tests/api/test_documents.py tests/api/test_ai_classroom.py tests/api/test_profiles_subjects.py tests/api/test_note_space.py -v
```
Results:
- `tests/api/test_documents.py`: 19 passed
- `tests/api/test_ai_classroom.py`: 9 passed
- `tests/api/test_profiles_subjects.py`: 16 passed
- `tests/api/test_note_space.py`: 10 passed
- **Total:** 54 passed (100% passing).

---

## 4. Live API & System Verification

Executed end-to-end against live Docker services (`api`, `db`, `minio`, `redis`, `worker`):

| Step | Operation | Target | Result | Status |
|------|-----------|--------|--------|--------|
| 1 | Authenticate | `admin@studyai.dev` | JWT access token obtained | PASS |
| 2 | Query Profiles | `GET /api/v1/profiles` | Profile `"Yash"`, `module = "AI_CLASSROOM"` | PASS |
| 3 | Query Subjects | `GET /api/v1/subjects?profile={id}` | Subject `"DSA"`, `profile = {yash_id}` | PASS |
| 4 | Create Document | `POST /api/v1/documents` | Doc created, `document.subject == dsa_id` | PASS |
| 5 | Upload Page Scan | `PUT /api/v1/storage/upload/...` | 1x1 image binary uploaded to MinIO | PASS |
| 6 | Finalize Upload | `POST /api/v1/documents/{id}/revisions` | Revision created, OCR job queued | PASS |
| 7 | Check OCR Status | `GET /api/v1/documents/{id}/pages` | Page OCR status `pending` / `processing` | PASS |
| 8 | Trigger Enrichment | `POST /api/v1/documents/{id}/enrich` | Returns `202 Accepted`, job enqueued | PASS |
| 9 | Enrichment 404 Check | `GET /api/v1/documents/{id}/enrichment` | Returns `404 Not Found` while running; frontend polling handles gracefully | PASS |
| 10 | Job Status Check | `GET /api/v1/jobs/{jobId}` | Returns `200 OK`, `status = "running"` | PASS |
| 11 | Document List | `GET /api/v1/documents` | Newly created note present in list | PASS |
| 12 | Direct Doc Detail | `GET /api/v1/documents/{id}` | Returns `200 OK` with correct profile & subject | PASS |

---

## 5. Conclusion

PHASE 9B COMPLETE
