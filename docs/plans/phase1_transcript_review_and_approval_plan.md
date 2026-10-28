# StudyAI — Phase 1: Handwritten Note Transcript Review and Approval Workflow Implementation Plan

**Branch:** `feature/transcript-review-and-approval-workflow`  
**Base Commit:** `691b5f7` (branched from `main`)  
**Status:** In Progress (Plan Documented & Execution Starting)  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)  

---

## 1. Overview and Objectives

Following the read-only Phase 0 investigation ([`docs/audits/phase0_transcription_and_review_audit.md`](file:///Users/yash/CV_Project/StudyAI/docs/audits/phase0_transcription_and_review_audit.md)), this plan executes the implementation of a student transcript-review and approval workflow.

### Core Problems Being Solved:
1. **Unchecked Automatic Indexing [Critical F-01]:** In [`backend/apps/documents/services.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/documents/services.py#L305), `run_ocr_job` unconditionally enqueues indexing upon raw OCR completion. This embeds unverified text into pgvector without student consent or quality verification.
2. **Canvas Transcript Invisibility [Critical F-02]:** In [`frontend/src/features/notes/HandwrittenView.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/features/notes/HandwrittenView.tsx), canvas notes exclusively render the stroke replay. The transcribed text is completely omitted from the UI.
3. **Read-Only Transcript Viewer [High F-03]:** In [`frontend/src/features/notes/components/TranscriptPanel.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/features/notes/components/TranscriptPanel.tsx), scanned note lines are rendered as static read-only `<div>` text. There are no editing, reordering, deletion, or approval controls.
4. **Test Suite Flakiness with Live Ollama Multimodal:** Integration tests in [`tests/api/test_documents.py`](file:///Users/yash/CV_Project/StudyAI/tests/api/test_documents.py) that pass dummy `b"fake-image"` bytes fail when live Ollama rejects invalid image payloads. Proper mocking and testing must be in place.
5. **Absence of OCR Evaluation Harness [Medium F-05]:** Lack of automated CER/WER evaluation utilities in `tests/evaluation/`.

---

## 2. Architecture & Design Principles

### The State Machine
```text
  [ Canvas Saved / Scan Uploaded ]
                │
                ▼
         [ OCR_PENDING ]
                │
                ▼ (Celery worker claims job)
        [ OCR_PROCESSING ]
         │              │
         │ (success)    │ (fatal failure)
         │              ▼
         │         [ OCR_FAILED ]
         │          (Student clicks Retry OCR -> back to OCR_PENDING)
         ▼
  mean confidence < 0.80 ?
     ├── YES ──► [ NEEDS_REVIEW ]
     └── NO  ──► [ PENDING_REVIEW ]
                      │
     ┌────────────────┴────────────────┐
     ▼                                 ▼
[ Student clicks "Approve" ]   [ Student edits lines & saves ]
     │                                 │
     └────────────────┬────────────────┘
                      ▼
                 [ APPROVED ]
                      │
                      ▼
         [ Enqueue Indexing Job ]
      (Generates NoteChunks & pgvector 1024-dim embeddings)
```

### Key Decisions Applied:
- **Approval Granularity:** Page-level approval with document-level rollup. Indexing occurs when all pages of the document are approved.
- **Searchability Gating:** Strict knowledge base gating. Unapproved transcripts are **never** indexed in pgvector or FTS. They do not appear in AI Chat citations or enrichment until student approval.
- **Canvas UI Layout:** Responsive layout with side-by-side view on desktop (strokes on the left, transcript on the right) and tabbed switcher on mobile.
- **User Edit Semantics:** Saving an edit creates an immutable revision, automatically transitions the page to `APPROVED`, and triggers indexing.
- **Historical Migration:** Backfill existing `READY` documents to `review_status='approved'` and `is_approved=True` to preserve existing notes without disruption.

---

## 3. Step-by-Step Implementation Plan

### Step 1: Database Model & Schema Migration
- File: [`backend/apps/documents/models.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/documents/models.py)
  - Add `ReviewStatus` text choices to `DocumentPage`:
    - `OCR_PENDING = "ocr_pending"`
    - `OCR_PROCESSING = "ocr_processing"`
    - `OCR_FAILED = "ocr_failed"`
    - `NEEDS_REVIEW = "needs_review"`
    - `PENDING_REVIEW = "pending_review"`
    - `APPROVED = "approved"`
  - Add fields to `DocumentPage`:
    - `review_status = models.CharField(max_length=32, choices=ReviewStatus.choices, default=ReviewStatus.OCR_PENDING, db_index=True)`
    - `is_approved = models.BooleanField(default=False, db_index=True)`
    - `approved_at = models.DateTimeField(null=True, blank=True)`
    - `approved_by = models.ForeignKey("profiles.Profile", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_pages")`
- Migration:
  - Generate schema migration with `makemigrations`.
  - Add a data migration operation backfilling all `DocumentPage` records whose `document.status == 'READY'` to `review_status = 'approved'`, `is_approved = True`.
  - Apply migration with `manage.py migrate`.

### Step 2: Backend Business Logic & Celery Job Decoupling
- File: [`backend/apps/documents/services.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/documents/services.py)
  - In `run_ocr_job`:
    - On OCR success:
      - Calculate page mean confidence.
      - If mean < 0.80 or illegible: set `page.review_status = DocumentPage.ReviewStatus.NEEDS_REVIEW`.
      - Else: set `page.review_status = DocumentPage.ReviewStatus.PENDING_REVIEW`.
      - Set `page.save(update_fields=["review_status", "updated_at"])`.
      - **REMOVE** `enqueue_index_job(page.document)` from line 305!
    - On OCR failure:
      - Set `page.review_status = DocumentPage.ReviewStatus.OCR_FAILED`.
  - In `IngestionService.create_user_revision`:
    - Set `page.review_status = DocumentPage.ReviewStatus.APPROVED`, `is_approved = True`, `approved_at = timezone.now()`, `approved_by = editor_profile`.
    - Keep `enqueue_index_job(page.document)` so edited revisions are immediately indexed.
  - Implement `IngestionService.approve_page(page, profile)`:
    - Set `page.review_status = DocumentPage.ReviewStatus.APPROVED`, `is_approved = True`, `approved_at = timezone.now()`, `approved_by = profile`.
    - Check if all pages for `page.document` are approved (`document.pages.filter(is_approved=False).exists()`).
    - If all pages are approved: ensure `document.status = Document.Status.READY` and call `enqueue_index_job(page.document)`.
    - Return `(page, all_pages_approved)`.
  - Implement `IngestionService.retry_page_ocr(page, profile)`:
    - Set `page.review_status = DocumentPage.ReviewStatus.OCR_PENDING`.
    - Call `enqueue_ocr_job(page)`.

### Step 3: API Endpoints & Serializers
- File: [`backend/apps/documents/serializers.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/documents/serializers.py)
  - Expose `review_status`, `is_approved`, `approved_at` on `DocumentPageSerializer`.
- File: [`backend/apps/documents/views.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/documents/views.py)
  - Add `DocumentPageApproveView(APIView)`:
    - `POST /api/v1/documents/{document_id}/pages/{page_id}/approve`
    - RLS profile isolation check.
    - Calls `IngestionService.approve_page`.
    - Returns `200 OK` with `{ page_id, review_status: "approved", is_approved: true, all_pages_approved: bool }`.
  - Add `DocumentPageRetryOcrView(APIView)`:
    - `POST /api/v1/documents/{document_id}/pages/{page_id}/retry-ocr`
    - Calls `IngestionService.retry_page_ocr`.
    - Returns `202 Accepted` with `{ page_id, job_id, review_status: "ocr_pending" }`.
- File: [`backend/apps/documents/urls.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/documents/urls.py)
  - Register the two new routes.

### Step 4: Frontend Transcript Review & Approval UI
- File: [`frontend/src/features/notes/types.ts`](file:///Users/yash/CV_Project/StudyAI/frontend/src/features/notes/types.ts)
  - Update `DocumentPage` interface with `review_status`, `is_approved`, `approved_at`.
- File: [`frontend/src/features/notes/useDocument.ts`](file:///Users/yash/CV_Project/StudyAI/frontend/src/features/notes/useDocument.ts)
  - Add mutations:
    - `approvePage(documentId: string, pageId: string)`
    - `savePageRevision(documentId: string, pageId: string, lines: Array<{ line_index: number, text: string }>)`
    - `retryPageOcr(documentId: string, pageId: string)`
- File: [`frontend/src/features/notes/components/TranscriptPanel.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/features/notes/components/TranscriptPanel.tsx)
  - Upgrade to an interactive transcript review component:
    - Display line cards with line numbering and confidence indicator.
    - Inline editing capability: click to edit text, add line above/below, delete line, move line up/down.
    - Top action bar:
      - Review status badge: "Needs Review" (amber), "Awaiting Review" (blue), "Approved" (green), "Processing" (pulse).
      - "Approve Transcript" button (primary teal/emerald) when not approved.
      - "Edit Transcript" toggle button.
      - "Re-run OCR" button.
      - Save changes button when in edit mode (creates revision and auto-approves).
- File: [`frontend/src/features/notes/HandwrittenView.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/features/notes/HandwrittenView.tsx)
  - Fix canvas invisibility:
    - If `isCanvas`: render split view (left: `<CanvasReplay>`, right: `<TranscriptPanel>`) on `md:` breakpoints, with a toggleable tab bar `[Drawing | Transcript]` on mobile.
    - If uploaded scan: render preview on left, `<TranscriptPanel>` on right.

### Step 5: Test Harness & Evaluation
- File: [`tests/api/test_documents.py`](file:///Users/yash/CV_Project/StudyAI/tests/api/test_documents.py)
  - Add proper mocks for `Qwen35OCRProvider` in tests using dummy byte strings (`b"fake-image"`) so live Ollama is not sent unparsable payloads.
  - Add test: `test_ocr_completion_does_not_auto_index` (confirms `enqueue_index_job` is NOT triggered by OCR).
  - Add test: `test_page_approve_endpoint_triggers_indexing` (confirms approving all pages triggers indexing).
  - Add test: `test_user_edit_auto_approves_and_reindexes` (confirms editing lines sets `approved=True` and indexes).
  - Add test: `test_page_retry_ocr_endpoint` (confirms retry initiates new OCR job).
- File: [`tests/evaluation/test_ocr_evaluation.py`](file:///Users/yash/CV_Project/StudyAI/tests/evaluation/test_ocr_evaluation.py)
  - Add CER (Character Error Rate) and WER (Word Error Rate) evaluation utility and unit tests.

### Step 6: Regression Verification & Production Build
- Run full backend test suite (`pytest tests/api/test_documents.py tests/api/test_canvas_ingestion.py`).
- Run frontend tests (`npm test`).
- Run frontend production build (`npm run build`).
- Verify container health.

---

## 4. Verification Gate Criteria
- Zero untracked schema discrepancies (`makemigrations --check`).
- All backend tests passing (`pytest tests/api/test_documents.py`).
- All frontend tests passing.
- Frontend build produces clean production assets without TypeScript errors.
- Document and Page models safely reflect `review_status` with zero regressions on existing data.
