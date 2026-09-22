# Phase 8 Frontend Audit — Complete User Flow Verification

## Executive Summary

- **Audit Target**: StudyAI React Frontend (`frontend/src`) against Django Backend (Phases 1–7).
- **Core User Journey**:
  $$\text{User} \rightarrow \text{Upload handwritten note} \rightarrow \text{OCR / processing status} \rightarrow \text{Note appears in notes} \rightarrow \text{Enrichment runs} \rightarrow \text{Enriched note available} \rightarrow \text{Open note} \rightarrow \text{See: original note, enriched content, explanations, textbook citations}$$
- **Audit Methodology**: Static architectural inspection of all routes, stores, components, and API services, paired with live API contract verification, network traffic inspection against running Docker containers (`studyai-frontend-1` and `studyai-api-1`), and end-to-end execution of the ingestion, OCR, and enrichment pipelines using real study note fixtures.
- **Auditor Constraint**: **AUDIT ONLY** — No frontend code modifications were implemented during this audit.

---

## 1. Overall Conclusion

```text
FRONTEND PARTIALLY CONNECTED
```

The frontend possesses the basic visual wireframes, routes, upload triggers, and layout components for handwritten notes, OCR review, and enrichment. However, **critical structural and state disconnects prevent a real user from successfully completing and persisting the intended product flow**:

1. **State Isolation**: Notes are loaded strictly from browser-local IndexedDB; `documentsApi.list()` is never invoked by the workspace store. Uploaded notes disappear on other devices, private tabs, or browser cache clears.
2. **Dead-End Note Detail**: `NoteDetailPage` has no remote fetch fallback (`documentsApi.get`). If the note is not in the local store slice, it fails with an unrecoverable error.
3. **Module Gating**: Default profiles are provisioned with `module: "NOTE_SPACE"` where `services.enrichment` is `false`. The frontend completely hides the `Enriched` tab and resets to `handwritten`.
4. **Enrichment Polling Race Condition**: When enrichment is triggered, the frontend immediately requests `GET /documents/{id}/enrichment`. Because the backend returns `404 Not Found` while the asynchronous Celery job is processing, the frontend classifies this as `"not_enriched"` and permanently terminates polling.
5. **Citations Broken as Student Anchors**: Citations strip all reference textbook metadata, book titles, and evidence quotes, converting them solely into page jumps within the student's handwritten scan.

---

## 2. Component & Capability Inventory

| Frontend Capability | Component / File | API Client Used | Status | Key Observation / Deficiency |
| :--- | :--- | :--- | :--- | :--- |
| **Login / Auth** | `frontend/src/features/auth/LoginPage.tsx`<br>`frontend/src/features/auth/authStore.ts` | `authApi.login`<br>`POST /api/v1/auth/login` | **COMPLETE** | Tokens stored in localStorage; Bearer auth and auto-refresh functional. |
| **Profile** | `frontend/src/components/layout/Sidebar.tsx`<br>`frontend/src/features/auth/authStore.ts` | `profilesApi.list`<br>`GET /api/v1/profiles` | **COMPLETE** | Profile switching and creation work; header `X-Active-Profile` sent. |
| **Notes List** | `frontend/src/components/subjects/SubjectWorkspace.tsx`<br>`frontend/src/components/folders/FolderDetailPage.tsx`<br>`frontend/src/state/workspaceStore.ts` | IndexedDB `allNotes()`<br>(`documentsApi.list` exists but unused) | **BROKEN** | Backend documents are never fetched into workspace store. Uploaded notes with `folderId: null` fail to match `"__unfiled__"`. |
| **Note Detail** | `frontend/src/components/notes/NoteDetailPage.tsx` | None (reads strictly from local store `notes.find()`) | **BROKEN** | Lacks remote fetch fallback `documentsApi.get(noteId)`. Direct navigation or refresh fails. |
| **Handwritten Upload** | `frontend/src/components/subjects/SubjectWorkspace.tsx`<br>`frontend/src/services/api/documents.ts` | `documentsApi.create`<br>`documentsApi.uploadToSignedUrl`<br>`documentsApi.finalizeUpload` | **PARTIAL** | Upload and signed URL flow works, but `subject: subjectId` is omitted in `create()` payload, severing subject association. |
| **OCR Status** | `frontend/src/components/notes/NoteRow.tsx`<br>`frontend/src/components/notes/HandwrittenView.tsx`<br>`frontend/src/components/ui/primitives.tsx` | `documentsApi.pages` | **BROKEN** | `NoteRow.tsx` hardcodes `<TranscriptionChip status="pending" />`. `HandwrittenView.tsx` fetches pages once on mount and never polls. |
| **Revision Display** | `frontend/src/components/notes/HandwrittenView.tsx` (`UploadSource`, `TranscriptPanel`) | `documentsApi.revisions`<br>`documentsApi.getPageDownloadUrl` | **COMPLETE** | Displays original note page scan image alongside transcribed lines once revision exists. |
| **Enrichment Trigger** | `frontend/src/components/notes/EnrichedView.tsx` (`generate`) | `enrichmentApi.generate`<br>`POST /documents/{id}/enrich` | **COMPLETE** | Successfully posts to backend and triggers asynchronous Celery job. |
| **Enrichment Status** | `frontend/src/components/notes/EnrichedView.tsx` | `enrichmentApi.get`<br>`GET /documents/{id}/enrichment` | **BROKEN** | Polling race condition: 404 returned while Celery runs immediately cancels polling, reverting UI to idle. |
| **Enriched Note Display** | `frontend/src/components/notes/EnrichedView.tsx` | `enrichmentApi.get` | **PARTIAL** | Correctly renders blocks and titles when data is present, but tab is hidden when `profile.module === "NOTE_SPACE"`. |
| **Citations** | `frontend/src/components/notes/EnrichedView.tsx`<br>`frontend/src/services/api/enrichment.ts` (`normalizeCitations`) | `enrichmentApi.get` | **BROKEN** | Strips `source_type`, `content`, and book title. Treats reference citations as student note scan page jumps. |
| **Error / Retry** | `frontend/src/components/ui/primitives.tsx` (`ErrorState`)<br>`frontend/src/components/notes/EnrichedView.tsx` | Various | **PARTIAL** | Has retry buttons in `EnrichedView` and `HandwrittenView`; upload errors in `SubjectWorkspace` are caught silently. |

---

## 3. Current Frontend Architecture

```text
Sidebar / Profile Switcher (Sidebar.tsx)
  │ [Active Profile: NOTE_SPACE or AI_CLASSROOM]
  ↓
Subject Workspace (SubjectWorkspace.tsx)
  │ Reads folders & notes from workspaceStore (IndexedDB only)
  │ File Input -> handleUpload()
  │   - documentsApi.create(profile.id, file.name)  [Drops subjectId!]
  │   - documentsApi.uploadToSignedUrl(upload.url, bytes)
  │   - documentsApi.finalizeUpload(doc.id, page.id)
  │   - workspaceStore.registerUploadNote({ folderId: null })
  ↓
Folder / Notes Listing (FolderDetailPage.tsx / NoteRow.tsx)
  │ Displays notes matching subjectId & folderId
  │ [Bug: notes with folderId: null do not appear under UNFILED_FOLDER_ID "__unfiled__"]
  │ [Bug: NoteRow hardcodes TranscriptionChip status="pending"]
  ↓
Note Detail Page (NoteDetailPage.tsx)
  │ [Bug: note = notes.find(...) -> if missing from local IndexedDB, renders loadFailed]
  │ Module Gating: checks useSubjectModule(subjectId)
  │   - If NOTE_SPACE: Enriched tab is hidden; forcefully resets to handwritten tab
  │   - If AI_CLASSROOM: Shows [Handwritten] and [Enriched] tabs
  ↓
  ├── Tab 1: Handwritten View (HandwrittenView.tsx)
  │     - documentsApi.pages(note.refId)
  │     - documentsApi.getPageDownloadUrl(page.id)
  │     - documentsApi.revisions(note.refId, page.id)
  │     [Bug: Loads once on mount; never polls for OCR completion]
  │
  └── Tab 2: Enriched View (EnrichedView.tsx)
        - enrichmentApi.get(note.refId)
        - "Generate" -> enrichmentApi.generate(note.refId) -> POST /documents/{id}/enrich (202)
        - Immediate refresh() -> GET /documents/{id}/enrichment (404)
        [Bug: 404 sets state="not_enriched", which terminates polling timer immediately]
        ↓
      Citation Chips (EnrichedView.tsx -> onCitation)
        [Bug: normalizeCitations discards reference textbook title and quote content;
         clicking citation navigates back to HandwrittenView on page N of student scan]
```

---

## 4. Backend / API Contract Verification

| Feature | Backend Endpoint | Frontend Call | Contract Matches? | Discrepancies & Contract Violations |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication** | `POST /api/v1/auth/login` | `authApi.login(email, pass)` | **YES** | Matches payload `{"email", "password"}`, returns `{"access", "refresh"}`. |
| **Profiles List** | `GET /api/v1/profiles` | `profilesApi.list()` | **YES** | Backend returns `{"results": [...]}`; frontend `toList()` unwraps correctly. |
| **Create Document** | `POST /api/v1/documents` | `documentsApi.create(profileId, name, "image")` | **PARTIAL** | Backend accepts `subject` UUID. Frontend does **not** pass `subject`, leaving `subject = null` in database. |
| **Upload Binary** | `PUT /api/v1/storage/upload/<key>?token=...` | `documentsApi.uploadToSignedUrl(url, blob, type)` | **YES** | Direct binary upload via signed URL returns 200/204. |
| **Finalize Upload** | `POST /api/v1/documents/{id}/revisions` | `documentsApi.finalizeUpload(docId, pageId)` | **YES** | Request `{"page_id": pageId}` creates revision and enqueues Celery OCR job. |
| **Fetch Pages** | `GET /api/v1/documents/{id}/pages` | `documentsApi.pages(docId)` | **YES** | Returns array of `DocumentPage` objects with `ocr_status`. |
| **Fetch Revisions** | `GET /api/v1/documents/{id}/revisions?page={pageId}` | `documentsApi.revisions(docId, pageId)` | **YES** | Returns array of revisions with line arrays and confidence scores. |
| **List Notes** | `GET /api/v1/documents` | `documentsApi.list()` | **CONTRACT EXISTS, UNUSED** | Backend supports `GET /api/v1/documents`. Frontend defined `documentsApi.list()` but **never calls it** in `workspaceStore.ts`. |
| **Trigger Enrichment** | `POST /api/v1/documents/{id}/enrich` | `enrichmentApi.generate(docId)` | **YES** | Request body `{}` returns HTTP 202 Accepted with `{"enriched_note": null, "job": {...}}`. |
| **Fetch Enrichment** | `GET /api/v1/documents/{id}/enrichment` | `enrichmentApi.get(docId)` | **CONTRACT MISMATCH ON PENDING** | While enrichment runs, backend returns HTTP 404 ("No enrichment exists"). Frontend treats 404 as `"not_enriched"` instead of `"enriching"`. |
| **Citations** | `GET /api/v1/documents/{id}/enrichment` (`blocks[].citation`) | `enrichmentApi.get` -> `normalizeCitations` | **CONTRACT MISMATCH ON SCHEMA** | Backend provides `source_type`, `content`, `chunk_id`, `verification_status`. Frontend only extracts `page_number`, discarding all textbook quotes. |

---

## 5. Detailed Inspection of Product Flow Stages

### 3. Handwritten Note Upload Flow
- **User Action**: User clicks "+ Upload" in `SubjectWorkspace.tsx` and selects an image (`.png` / `.jpg`).
- **Network Execution**:
  1. `POST /api/v1/documents` with payload `{"profile": "<uuid>", "source_type": "image", "filename": "cell_biology.png"}` $\rightarrow$ HTTP 201 Created.
  2. `PUT /api/v1/storage/upload/...` with image binary $\rightarrow$ HTTP 200 OK.
  3. `POST /api/v1/documents/<id>/revisions` with `{"page_id": "<pageId>"}` $\rightarrow$ HTTP 202 Accepted, dispatches Celery OCR job.
- **Frontend State Update**:
  - Store calls `registerUploadNote({ documentId, profileId, subjectId, folderId: null, title })`.
  - Store saves `NoteMeta` to IndexedDB and pushes to local `notes` array.
  - Automatically navigates to `/subjects/${subjectId}/notes/${documentId}`.
- **Failure Points**:
  - `documentsApi.create` omits `subject`. In the database, the document is saved with `subject = None`.
  - `registerUploadNote` sets `folderId: null`, which disconnects it from folder trees and unfiled listings.

### 4. OCR & Processing UX
- **Page Display**: On landing on `NoteDetailPage`, `HandwrittenView` mounts and calls:
  1. `GET /api/v1/documents/<id>/pages` $\rightarrow$ returns page with `ocr_status: "pending"`.
  2. `GET /api/v1/documents/pages/<id>/download` $\rightarrow$ returns signed image URL.
  3. Image renders immediately.
  4. If `p.current_revision_id` is null, renders: `"Transcription pending. Check back in a moment."`
- **Failure Points**:
  - **No Polling**: `HandwrittenView` executes `load()` once in a `useEffect`. It never polls the backend for OCR status changes. The user must manually reload the page to see transcribed lines.
  - **Hardcoded NoteRow**: In `NoteRow.tsx` (the folder/subject note list), line 36 contains `{note.source === "upload" && <TranscriptionChip status="pending" />}`, hardcoding `"pending"` regardless of backend OCR completion.

### 5. Note / Revision Display
- **Transcript Rendering**: When OCR completes and `current_revision_id` is populated, `TranscriptPanel` renders line-by-line transcription with line numbers and heading highlights.
- **Image Scan Rendering**: Renders full-width original image with zoom controls (50% to 200%) and page navigation.
- **Failure Point**:
  - If a user refreshes the page or opens the link in a fresh session, `workspaceStore.notes` is loaded from IndexedDB. If the local IndexedDB does not contain that note record, `notes.find(n => n.id === noteId)` returns `undefined`, and `NoteDetailPage` displays:
    ```tsx
    <p className="muted">{t("notes.detail.loadFailed")}</p>
    ```
    It makes no attempt to call `documentsApi.get(noteId)`.

### 6 & 7. Enrichment Trigger & Polling Race Condition
- **Trigger**: In `EnrichedView.tsx`, clicking "Generate enrichment" calls `enrichmentApi.generate(note.refId)`.
- **Backend Behavior**: `POST /documents/{id}/enrich` enqueues Celery enrichment job `run_enrichment_job` and returns `202 Accepted` with `{"job": {"id": "...", "status": "queued"}}`.
- **The Race Condition**:
  1. `EnrichedView.tsx` executes:
     ```typescript
     await enrichmentApi.generate(note.refId);
     await refresh(); // Calls GET /documents/{id}/enrichment
     ```
  2. Because the background Celery worker is still running, no `EnrichedNote` database record exists yet.
  3. Backend `enrichment()` action executes:
     ```python
     note = EnrichmentService.latest_note(request.user, str(pk))
     if note is None:
         raise ResourceNotFound("No enrichment exists for this document yet.")
     ```
     Returning **HTTP 404 Not Found**.
  4. `enrichmentApi.get` catches the 404 and returns `{ state: "not_enriched", blocks: [] }`.
  5. `EnrichedView`'s polling hook evaluates:
     ```typescript
     useEffect(() => {
       if (!snapshot || snapshot.state !== "enriching") {
         stopPolling();
         return;
       }
       // ... starts poll timer
     }, [snapshot?.state]);
     ```
  6. Because `snapshot.state` is `"not_enriched"` (not `"enriching"`), **it immediately stops polling**.
  7. The UI flashes for a millisecond and returns to the empty state with the "Generate enrichment" button. Polling never runs.

### 8 & 9. Enriched Note & Citation Display
- **Backend Schema**: When an enrichment completes, `GET /documents/{id}/enrichment` returns:
  ```json
  {
    "id": "c9cb1b98-9cc1-4895-b453-0409b3d73b3c",
    "document": "5e22472c-5056-4894-8f7f-f444f27264e5",
    "blocks": [
      {
        "block_index": 1,
        "block_type": "gap_fill",
        "title": "Oxidative Phosphorylation Mechanism",
        "content": "Oxidative phosphorylation produces ATP via chemiosmosis...",
        "citation": {
          "source_refs": [
            {
              "source_type": "reference",
              "chunk_id": "bb85d06b-789b-4125-b071-d9abb4606e0e",
              "document_id": "277010d6-0b0f-478f-a49e-2100f159bb63",
              "page_number": 164,
              "content": "Oxidative Phosphorylation and the Electron Transport Chain: In the inner mitochondrial membrane...",
              "retrieval_score": null
            }
          ],
          "verification_status": "supported",
          "verification_score": 1.0
        }
      }
    ]
  }
  ```
- **Frontend Ingestion**:
  In `frontend/src/services/api/enrichment.ts`:
  ```typescript
  function normalizeCitations(block: WireBlock): CitationRef[] {
    const refs = block.citation?.source_refs ?? [];
    return refs
      .filter((r) => typeof r.page_number === "number")
      .map((r) => ({
        page: r.page_number as number,
        bbox: Array.isArray(r.bbox) ? r.bbox.map(Number) : null,
      }));
  }
  ```
- **Disaster in Citation UX**:
  1. The citation chip renders: `<button className="citation-chip">Page 164</button>`.
  2. The reference quote ("Oxidative Phosphorylation..."), the fact that it is a reference textbook, and the verification status are **completely discarded**.
  3. When the user clicks the chip, `onCitation(164)` in `NoteDetailPage.tsx` sets:
     ```typescript
     setPage(164);
     setTab("handwritten");
     ```
  4. It switches tabs to the student's own handwritten note scan and attempts to display page 164!
  5. The student note only has 1 page, so the viewer falls back or displays nothing. The reference evidence is completely inaccessible.

### 10. Profile Integration & Module Gating
- **Module Matrix Lockout**:
  - Profiles default to `module: "NOTE_SPACE"` (`Profile.objects.create(..., module="NOTE_SPACE")`).
  - In `frontend/src/types/modules.ts`:
    ```typescript
    NOTE_SPACE: { transcription: true, write: true, enrichment: false, ... }
    AI_CLASSROOM: { transcription: true, write: true, enrichment: true, ... }
    ```
  - In `NoteDetailPage.tsx`:
    ```tsx
    {services.enrichment ? (
      <div className="tabs" role="tablist">
        <TabButton active={tab === "handwritten"}>Handwritten</TabButton>
        <TabButton active={tab === "enriched"}>Enriched</TabButton>
      </div>
    ) : null}
    ```
  - And:
    ```typescript
    useEffect(() => {
      if (!services.enrichment && tab === "enriched") {
        setTab("handwritten");
      }
    }, [services.enrichment, tab]);
    ```
  - **Result**: Unless the user is onboarded with or manually switches to an `AI_CLASSROOM` profile, the `Enriched` tab is hidden. Any attempt to access enrichment is redirected to `handwritten`.
- **Unfiled Folder Note Disconnect**:
  - `SubjectWorkspace.tsx` registers uploaded notes with `folderId: null`.
  - In `SubjectWorkspace.tsx`, `unfiledCount` is calculated as:
    `notes.filter(n => n.subjectId === subjectId && n.folderId === UNFILED_FOLDER_ID).length`
    Since `null !== "__unfiled__"`, `unfiledCount` is `0`.
  - In `FolderDetailPage.tsx` for `__unfiled__`, notes are filtered with:
    `notes.filter(n => n.subjectId === subjectId && n.folderId === folderId)`
    Since `null !== "__unfiled__"`, `folderNotes` is empty. The uploaded note does not appear under Unfiled Notes.

---

## 6. Multi-State UI Scorecard

| UI State | Handled in Frontend? | Component / Implementation | Evaluation |
| :--- | :--- | :--- | :--- |
| **No note** | **YES** | `EmptyState` in `SubjectWorkspace.tsx` | Clean empty state with "New Folder" and "Write" actions. |
| **Uploading** | **YES** | `uploading` state in `SubjectWorkspace.tsx` | Disables input and changes label to "Uploading…". |
| **OCR processing** | **PARTIAL** | `TranscriptionChip` in `HandwrittenView.tsx` | Shows "Transcription pending", but no live progress or polling. |
| **OCR failed** | **PARTIAL** | `TranscriptionChip status="failed"` | Renders failed chip; retry button only re-fetches existing DB record. |
| **Ready for enrichment** | **YES** | `EmptyState` in `EnrichedView.tsx` | Displays sparkle icon with "Generate enrichment" button. |
| **Enrichment processing** | **BROKEN** | `enrichment-progress` in `EnrichedView.tsx` | Component exists with pulse animation, but polling race condition prevents state from staying active. |
| **Enrichment complete** | **YES** | `enriched-body` in `EnrichedView.tsx` | Renders blocks, headings, paragraphs, and tags. |
| **Enrichment failed** | **YES** | `ErrorState` in `EnrichedView.tsx` | Shows failure title, message, and retry button (`onRetry={() => generate()}`). |
| **Enrichment stale** | **YES** | `stale-note` alert in `EnrichedView.tsx` | Shows "This enrichment is out of date" with a "Regenerate" button. |
| **No gaps found** | **NOT EXPOSED** | None | Backend gap detection does not distinguish zero-gap state in frontend UI. |
| **Gaps found** | **PARTIAL** | Renders as standard block type `gap_fill` | Rendered alongside overview blocks; no visual distinction between gap-fill and overview blocks. |

---

## 7. Stale Frontend Implementation & Architecture Heritage

| Term / Artifact | Occurrences in Frontend | Classification | Impact |
| :--- | :--- | :--- | :--- |
| **`qwen2.5`** | 0 occurrences in `frontend/` | **ABSENT** | Frontend never referenced model names directly. |
| **`candidate generation`** | 0 occurrences in `frontend/` | **ABSENT** | Candidate generation details remain encapsulated in backend. |
| **`candidate validation`** | 0 occurrences in `frontend/` | **ABSENT** | Verification status passed via citation block. |
| **`verificationStatus`** | Present in `AgentMessageBubble.tsx` and `useAgentChat.ts` | **ACTIVE (CHAT ONLY)** | Chat bubbles consume verification scores; note citations ignore it. |
| **`source_refs`** | `frontend/src/services/api/enrichment.ts` | **BROKEN / STALE ASSUMPTION** | Assumes `source_refs` only contain `page_number` from student note scans. |
| **`ai_stale`** | `frontend/src/services/api/enrichment.ts` | **ACTIVE** | Correctly maps backend `ai_stale` flag to `out_of_date` UI state. |
| **`NOTE_SPACE` service gate** | `frontend/src/types/modules.ts`<br>`frontend/src/components/notes/NoteDetailPage.tsx` | **BLOCKING / STALE ASSUMPTION** | Assumes NoteSpace users cannot view enrichments, hiding the feature from default accounts. |

---

## 8. Final Product Flow Scorecard

| User Journey Step | Status | Concrete Evidence | Specific Issue |
| :--- | :--- | :--- | :--- |
| **1. Login** | **WORKING** | `POST /api/v1/auth/login` returns JWT access/refresh. Persisted in `localStorage`. | None. |
| **2. Profile opens** | **WORKING** | `GET /api/v1/profiles` loads profiles; active profile set in header `X-Active-Profile`. | Defaults to `NOTE_SPACE`. |
| **3. Upload handwritten note** | **WORKING** | Native file picker accepts image; reads binary into `ArrayBuffer`. | None. |
| **4. Upload reaches backend** | **PARTIAL** | `POST /documents` + `PUT /storage/upload` + `POST /revisions` succeed. | `subjectId` dropped from `POST /documents` payload. |
| **5. OCR processing visible** | **BROKEN** | Shows initial status on mount. | No polling or WebSocket; `NoteRow.tsx` hardcodes status `"pending"`. |
| **6. Note/revision appears** | **PARTIAL** | Appears in local IndexedDB session only. | Remote notes never fetched via `documentsApi.list()`. Direct refresh fails. Uploaded note with `folderId: null` does not show in Unfiled Notes. |
| **7. Enrichment triggered** | **WORKING** | `POST /documents/{id}/enrich` returns HTTP 202 with job ID. | None. |
| **8. Enrichment status visible** | **BROKEN** | UI flashes and returns to "Generate enrichment". | Backend 404 while job runs terminates polling timer immediately. |
| **9. Enriched note displayed** | **PARTIAL** | Renders blocks if loaded after manual refresh on `AI_CLASSROOM` profile. | Hidden by default on `NOTE_SPACE` profiles. |
| **10. Citations displayed** | **BROKEN** | Renders "Page X" button. | Strips textbook name and quote; jumps to student scan instead of reference book. |
| **11. Refresh/reopen works** | **BROKEN** | Refreshing `/subjects/:sId/notes/:nId` renders `loadFailed`. | Store only checks IndexedDB; no remote API fallback. |
| **12. Enrichment failure handled** | **WORKING** | Failed state renders error title, message, and retry button. | None. |
| **13. Complete profile flow** | **BROKEN** | User cannot complete journey from upload to reopening persisted enrichment with citations. | Multiple P0/P1 blockers identified below. |

---

## 9. Classification of Issues

### P0 — Product Blockers (Core Flow Broken)

1. **P0-1: Remote Notes Never Loaded into Workspace Store (`workspaceStore.ts`)**
   - **Root Cause**: `loadWorkspace()` in `frontend/src/state/workspaceStore.ts` populates `notes` strictly from IndexedDB `allNotes()`. `documentsApi.list()` is never called.
   - **Impact**: When a user logs in on a new device, opens a private window, or clears local cache, their notes list is completely empty.
2. **P0-2: Note Detail Load Failure on Direct URL or Refresh (`NoteDetailPage.tsx`)**
   - **Root Cause**: `NoteDetailPage.tsx` uses `const note = notes.find((n) => n.id === noteId)`. If `note` is not in the Zustand store slice, it immediately renders `t("notes.detail.loadFailed")`.
   - **Impact**: Direct links, bookmarking, and page refreshes fail with a dead-end error even though the note exists on the backend.
3. **P0-3: Enrichment Polling Race Condition Dead-End (`EnrichedView.tsx` & `enrichment.ts`)**
   - **Root Cause**: Triggering enrichment calls `POST /documents/{id}/enrich` (202), followed immediately by `refresh()` (`GET /documents/{id}/enrichment`). While the Celery job is running, the backend returns 404 ("No enrichment exists"). `enrichmentApi.get` catches the 404 and returns `{ state: "not_enriched" }`. `EnrichedView` stops polling whenever `state !== "enriching"`.
   - **Impact**: Polling stops before it starts. The UI stays on "Generate enrichment". The user never sees the job finish unless they manually refresh the page after Celery completes.
4. **P0-4: Default Profile Module Gating Hides Enriched Tab (`NoteDetailPage.tsx` & `ModuleContext.tsx`)**
   - **Root Cause**: Default profiles are created with `module = "NOTE_SPACE"`. In `MODULE_SERVICE_MATRIX`, `NOTE_SPACE.enrichment = false`. `NoteDetailPage.tsx` suppresses the `Enriched` tab and resets to `handwritten` when `services.enrichment` is false.
   - **Impact**: Users with standard profiles cannot view or trigger enrichment.

---

### P1 — Required for Usable MVP (Important Feature Gaps)

5. **P1-1: Citations Treated as Student Note Anchors Instead of Textbook References (`EnrichedView.tsx`, `enrichment.ts`)**
   - **Root Cause**: `normalizeCitations()` in `enrichment.ts` strips `source_type`, `content`, and book titles, keeping only `page_number`. In `NoteDetailPage.tsx`, clicking a citation chip calls `onCitation(page)` which navigates the student's handwritten scan.
   - **Impact**: Reference textbook quotes and source citations (Requirement #9) cannot be viewed. Clicking a reference citation to page 164 attempts to jump the student's 1-page note to page 164.
6. **P1-2: Uploaded Notes Disconnected from Unfiled Folder (`SubjectWorkspace.tsx` & `FolderDetailPage.tsx`)**
   - **Root Cause**: `registerUploadNote` sets `folderId: null`. `SubjectWorkspace.tsx` checks `n.folderId === UNFILED_FOLDER_ID` (`"__unfiled__"`), and `FolderDetailPage.tsx` filters `n.folderId === folderId`.
   - **Impact**: Since `null !== "__unfiled__"`, unfiled notes show count 0 in the workspace and do not appear inside the Unfiled Notes folder view.
7. **P1-3: Document Creation Drops Subject (`SubjectWorkspace.tsx`)**
   - **Root Cause**: `documentsApi.create(profile.id, file.name, "image")` omits `subject: subjectId`.
   - **Impact**: In the database, the document is saved with `subject = None`, severing its association with subject-scoped study materials.
8. **P1-4: Hardcoded Pending OCR Chip and No Live OCR Polling (`NoteRow.tsx` & `HandwrittenView.tsx`)**
   - **Root Cause**: `NoteRow.tsx` hardcodes `<TranscriptionChip status="pending" />`. `HandwrittenView.tsx` fetches page statuses once on mount and never polls for OCR completion.
   - **Impact**: Users must manually refresh to find out if OCR transcription finished, and note list rows always display "pending".

---

### P2 — Cosmetic / Enhancements

9. **P2-1: Silent Failure on Upload Error (`SubjectWorkspace.tsx`)**
   - **Root Cause**: `handleUpload` has an empty catch block with `// TODO: surface upload error to user`.
   - **Impact**: Network failures or rejection during upload show no error toast or feedback to the user.
10. **P2-2: Missing Dedicated Jobs Client Service**
    - **Root Cause**: Frontend lacks a client for `/api/v1/jobs/{id}` to poll generic background jobs.
    - **Impact**: Enrichment and OCR status rely on querying resource endpoints rather than job state trackers.

---

## 10. Minimal Frontend Changes Required

To make the complete flow (`Upload handwritten note -> Processing -> Enrichment -> Profile display -> Citations`) fully operational, the following minimal set of targeted changes is required:

1. **`workspaceStore.ts`**:
   - In `loadWorkspace()`, fetch remote documents via `documentsApi.list()` and merge them into `notes`.
   - Map remote `DocumentInfo` records into `NoteMeta` with `folderId: UNFILED_FOLDER_ID` if unfiled.
2. **`NoteDetailPage.tsx`**:
   - When `note` is not found in store, fetch it directly via `documentsApi.get(noteId)`.
   - Enable the `Enriched` tab for any document that has or can have enrichment, or ensure the active profile supports enrichment.
3. **`enrichment.ts` & `EnrichedView.tsx`**:
   - When `enrichmentApi.generate()` returns `{ queued: true, jobId }`, set state to `"enriching"` and poll until the job status becomes `"completed"` or `GET /enrichment` returns `200`.
   - Do not stop polling when receiving a 404 while `enriching` is active.
4. **Citation Extraction & Modal/Popover (`enrichment.ts`, `EnrichedView.tsx`)**:
   - Preserve `source_type`, `content`, and book title in `normalizeCitations`.
   - If `source_type === "reference"`, render a citation badge (e.g. `[Ref: p. 164]`) that displays the cited textbook excerpt in a popover or expandable card rather than navigating the student's handwritten scan.
5. **`SubjectWorkspace.tsx`**:
   - Pass `subject: subjectId` in `documentsApi.create(profile.id, file.name, "image", subjectId)`.
   - Set `folderId: UNFILED_FOLDER_ID` when registering the upload note.
6. **`HandwrittenView.tsx` & `NoteRow.tsx`**:
   - In `HandwrittenView.tsx`, poll `documentsApi.pages(note.refId)` if any page has `ocr_status === "pending"`.
   - In `NoteRow.tsx`, display the actual OCR status rather than hardcoded `"pending"`.

---

## 11. Final Assessment

> **Can a real user go from uploading a handwritten note to reopening that note from their profile and seeing the persisted enriched result with its reference citations?**

**No.** Based on live execution against the running system:
1. When uploaded, the note drops its subject and is only saved to the browser's local IndexedDB.
2. If opened under a default profile, the Enriched tab is hidden.
3. If enrichment is triggered, the polling loop terminates instantly on the first 404, stranding the user on the empty state.
4. If reopened on another device or after cache clear, the note fails to load entirely.
5. Even if an enriched note is loaded, its citations point back to nonexistent pages of the student's own handwritten note rather than showing the reference textbook excerpts.
