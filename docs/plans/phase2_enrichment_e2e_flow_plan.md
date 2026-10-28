# StudyAI — Phase 2: Generate Enrichment End-to-End Flow Implementation Plan

**Branch:** `feature/enrichment-e2e-flow-and-approval-gating`  
**Base Commit:** `9be78dd` (`main`)  
**Status:** Proposed — Ready for Review  
**Author:** Antigravity (Google DeepMind Advanced Agentic Coding)

---

## 1. Objectives

1. Eliminate the race condition where `POST /documents/{id}/enrich` is executed while OCR is still running, which caused false `blank_content` classifications and permanently stuck "insufficient content" states.
2. Enforce strict approval gating on enrichment: a note cannot be enriched until its transcript has been reviewed and approved by the student.
3. Prevent LangGraph's `retrieve_chunks_node` from bypassing approval to silently index unapproved transcripts into pgvector.
4. Enhance the frontend `EnrichedView.tsx` with dedicated states for in-flight OCR transcription and pending transcript review, preventing premature button clicks and providing a seamless "Approve & Generate" one-click action.
5. Fix the brittle test assertion in `test_ai_classroom.py` for `generation_method`.

---

## 2. Step-by-Step Implementation Plan

### Step 1: Backend Precondition Validation in `EnrichmentService.enqueue_enrichment`
- **File:** [`backend/apps/ai_classroom/services.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/ai_classroom/services.py)
- **Changes:**
  - Before enqueuing an `enrich` job, inspect all pages belonging to the document:
    ```python
    from apps.documents.models import DocumentPage
    
    # Check 1: In-flight OCR
    processing_pages = document.pages.filter(
        review_status__in=[DocumentPage.ReviewStatus.OCR_PENDING, DocumentPage.ReviewStatus.OCR_PROCESSING]
    )
    if processing_pages.exists():
        raise ValidationError("Note transcription is still processing. Please wait for transcription to complete before enriching.")

    # Check 2: Transcript Approval Gating
    unapproved_pages = document.pages.filter(is_approved=False)
    if unapproved_pages.exists():
        raise ValidationError("Note transcript must be approved before generating enrichment.")
    ```

### Step 2: Content Gate Guard & Resilience in `run_enrichment_job`
- **File:** [`backend/apps/ai_classroom/services.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/ai_classroom/services.py)
- **Changes:**
  - In `run_enrichment_job`:
    - Check if any pages have active OCR jobs or unfinalized revisions before running `validate_note_academic_content`.
    - If in-flight OCR is detected, cancel or reschedule the job with an error rather than creating a permanent `EnrichedNote(empty_reason="blank_content")`.

### Step 3: Align LangGraph `retrieve_chunks_node` with Approval Boundary
- **File:** [`backend/apps/ai_classroom/enrichment_nodes.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/ai_classroom/enrichment_nodes.py)
- **Changes:**
  - In `retrieve_chunks_node`:
    - Remove the silent unconditional indexing:
      ```python
      # Replace:
      if not user_chunks and document.pages.exclude(current_revision_id=None).exists():
          from apps.retrieval.services import index_document
          index_document(document)
      ```
    - Check if all pages are approved (`not document.pages.filter(is_approved=False).exists()`).
      - If approved: index if chunks missing.
      - If unapproved: do NOT index into pgvector; raise an exception.

### Step 4: Frontend `EnrichedView.tsx` State Awareness & "Approve & Enrich" Action
- **File:** [`frontend/src/components/notes/EnrichedView.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/notes/EnrichedView.tsx)
- **Changes:**
  - Fetch the note's document pages using `documentsApi.listPages(docId)` on mount and when refreshing.
  - Compute page readiness:
    - `isTranscribing`: any page has `review_status === "ocr_pending" || review_status === "ocr_processing"`
    - `needsApproval`: `!isTranscribing && pages.some(p => !p.is_approved)`
  - Render explicit UI states:
    1. **`isTranscribing`**:
       - Icon: Spinning AI / Sparkle
       - Title: *"Transcribing your note..."*
       - Description: *"StudyAI is reading your handwriting with AI. Transcribed lines will appear shortly."*
       - Polling: Auto-poll page state every 2.5s.
    2. **`needsApproval`**:
       - Icon: Note with checkmark
       - Title: *"Review your transcript first"*
       - Description: *"To ensure high-quality AI notes and accurate textbook citations, review and approve your note transcript before generating enrichment."*
       - Buttons:
         - **"Review Transcript"** (switches to handwritten view)
         - **"Approve & Generate Enrichment"** (calls `approvePage` for unapproved pages, then kicks off `generate()`)
    3. **`isApproved && not_enriched`**:
       - Normal "Your enriched notes aren't ready yet." with active "Generate enrichment" button.
    4. **`insufficient_content`**:
       - Preserved: "Not enough academic content yet" with "Edit Handwritten Note".

### Step 5: Test Suite Updates
- **File:** [`backend/tests/api/test_ai_classroom.py`](file:///Users/yash/CV_Project/StudyAI/backend/tests/api/test_ai_classroom.py)
  - In `test_enrich_end_to_end_creates_verified_note`:
    - Update assertion to check that `methods` is a subset of valid choices:
      `self.assertTrue(methods.issubset({"llm", "rule_based", "transcribed", "user_edited"}))`
  - Add test: `test_enqueue_enrichment_rejected_if_ocr_in_progress`
  - Add test: `test_enqueue_enrichment_rejected_if_transcript_unapproved`
  - Add test: `test_enqueue_enrichment_succeeds_when_pages_approved`
- **File:** [`backend/tests/api/test_documents.py`](file:///Users/yash/CV_Project/StudyAI/backend/tests/api/test_documents.py)
  - Ensure documents API tests reflect approval before enrichment.

---

## 3. Verification Criteria
1. Zero premature `blank_content` false-positives when clicking between tabs during OCR.
2. Strict adherence to Phase 1 searchability gating: unapproved transcripts never enter pgvector or LangGraph.
3. User on `EnrichedView` is guided with clean feedback ("Transcribing...", "Review transcript first", or one-click "Approve & Generate").
4. All 38+ backend tests passing.
5. All 81+ frontend tests passing.
6. Clean production build (`npm run build`).
