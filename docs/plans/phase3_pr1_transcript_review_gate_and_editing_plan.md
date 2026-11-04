# StudyAI: PR 1 End-to-End Implementation Plan — Transcript Review Gate & Editing

**Phase:** PR 1 of 3 (Prerequisite)  
**Branch:** `feature/topic-based-enrichment-corrective-rag`  
**Base:** `origin/main` (`9be78dd`)  
**Status:** Planned / Architecture Specification (Final Concurrency, Migration, and Chunking Guard Refinements)

---

## 1. Objective & Scope

PR 1 establishes the verified contract of **approved, stable student transcripts** upon which topic planning and enrichment depend. It ensures that raw OCR text is never indexed or enriched prematurely, that manual user edits are tracked with stable line identity (`lineage_id`) separate from raw machine OCR, that concurrent edits and approvals are protected via optimistic locking (HTTP 409 Conflict), that OCR retries obey bounded attempt limits and a fixed preprocessing ladder, that stuck OCR jobs (in `ocr_processing` or `ocr_pending`) are recovered by a watchdog with distinct queue/processing timeouts, that unapproved text is never searchable, that legacy multi-page chunks are cleanly retired without collisions, and that edits to already-approved transcripts trigger incremental per-page re-indexing and mark downstream enrichments stale without data loss.

---

## 2. Key Architecture & Behavioral Requirements

### 2.1 OCR Completion Review Invariant & Heuristic Validation
- `run_ocr_job` computes the page review status from deterministic validation rules, not confidence alone.
- **Rule Module:** Implemented in `backend/apps/documents/validation.py`.
- **Review Reason Criteria:** Sets `review_status = NEEDS_REVIEW` and records the triggering rule(s) in `review_reasons: list[str]` if any of the following hold:
  1. `[illegible]` marker appears in more than 15% of lines (`OCR_ILLEGIBLE_THRESHOLD = 0.15`).
  2. More than 30% of lines are flagged uncertain (`OCR_UNCERTAIN_THRESHOLD = 0.30`). A line is defined as "uncertain" if its `confidence_score < OCR_LINE_UNCERTAIN_THRESHOLD` (default 0.80 placeholder, to calibrate on real validation sets before merge).
  3. Repetition loop: 4 or more identical consecutive lines.
  4. Blank page or very low image resolution:
     - For canvas pages: "blank" means zero strokes in ink data (`cpage.strokes.count() == 0`), and resolution checks do not apply.
     - For uploaded images: computed by `compute_image_metrics(image_bytes)` in `apps/documents/validation.py` using PIL (pixel resolution < 300x300, or ink ratio < 0.005; placeholders marked to calibrate on real handwritten pages before merge).
  5. Heavy ink with almost no recognized text: ink ratio > 0.15 but fewer than 3 lines recognized (placeholder marked to calibrate on real handwritten pages before merge).
- If none of these trigger, sets `review_status = PENDING_REVIEW`.
- **Celery Execution Limits:** Celery OCR task sets `soft_time_limit = 540` (9 minutes), comfortably below the 10-minute processing watchdog timeout. The task catches `SoftTimeLimitExceeded`, transitions `page.ocr_status = 'failed'`, records error `"OCR worker time limit exceeded"`, and bumps `ocr_generation`.
- **Invariant:** OCR completion **never** calls `enqueue_index_job` or `enqueue_enrichment`.

---

### 2.2 Approval Idempotency, Revision Lock & Per-Page Indexing
- **Endpoint:** `POST /api/v1/documents/{document_id}/pages/{page_id}/approve`
- **Request Payload:**
  ```json
  {
    "expected_revision_number": 2
  }
  ```
- **Order of Checks on Approval:**
  1. **Ignored Page Check (422):** If `page.is_ignored == True`, return `HTTP 422 Unprocessable Content` ("Page is ignored; un-ignore before approving").
  2. **In-Flight OCR Check (409):** If `page.ocr_status in ['pending', 'processing']`, return `HTTP 409 Conflict` ("OCR is currently in progress").
  3. **Failed OCR Check (422):** If `page.ocr_status == 'failed'` and `page.current_revision is None`, return `HTTP 422 Unprocessable Content` ("Cannot approve a failed page without transcription").
  4. **Blank Page Check (422):** If `page.current_revision and page.current_revision.lines.count() == 0`, return `HTTP 422 Unprocessable Content` ("Cannot approve a blank page; use Ignore for blank pages.").
  5. **Stale Revision Check (409):** Let `current_rev = page.current_revision.revision_number if page.current_revision else 0`. If `expected_revision_number != current_rev`, return `HTTP 409 Conflict` with `latest_revision` in the error body.
- **Conditional Update Idempotency:**
  - Execute conditional update:
    ```python
    rows_updated = DocumentPage.objects.filter(
        id=page_id,
        is_approved=False,
    ).update(
        is_approved=True,
        review_status=DocumentPage.ReviewStatus.APPROVED,
        approved_at=timezone.now(),
        approved_by=user,
        needs_review=False,
    )
    ```
  - If 0 rows updated (`rows_updated == 0`): The page is already approved with this revision. Return `HTTP 200 OK` and do nothing else (idempotent short-circuit).
  - If 1 row updated (`rows_updated == 1`):
    - Increment `page.index_epoch += 1` to ensure fresh indexing job identity on repeated approve/reopen/approve cycles.
    - Call the shared workflow synchronization helper `sync_page_approval_and_indexing(document, page)`.
- **Index Job Key & `index_epoch` (No Skipped Indexing on Approve $\rightarrow$ Reopen $\rightarrow$ Approve):**
  - Track `index_epoch = models.PositiveIntegerField(default=0)` on `DocumentPage`, incremented whenever indexing is triggered.
  - Job key: `idempotency_key = f"index_page:{page.pk}:{page.current_revision_id}:{page.index_epoch}:{_model_version()}"`.
  - This allows multiple distinct indexing jobs across lifecycle re-approvals while deduplicating in-flight tasks for the same epoch.
  - The job checks if `page.indexed_text_hash == page.current_revision.text_hash` and exits cleanly if already indexed.
  - Indexing is enqueued inside `transaction.on_commit` directly from `sync_page_approval_and_indexing`.
- **Periodic Reconcile Task:**
  - Periodic Celery task `reconcile_unindexed_pages_task` runs every 5 minutes:
    - Queries pages where `is_approved=True, is_ignored=False`.
    - Compares `page.current_revision.text_hash != page.indexed_text_hash`.
    - **Skip Rules:** Skips ignored pages, unapproved pages, pages with an active index job in progress (`status in ['queued', 'running']`), and pages whose last index job failed permanently (`Job.Status.FAILED_DEAD_LETTER`).
    - Storing `indexed_text_hash` ensures blank approved pages are marked as reconciled and do not loop endlessly.
- **Legacy Pages & Reconcile Safety:**
  - In migration `0010_transcript_data_backfill.py`, `indexed_text_hash` is initialized to `current_revision.text_hash` for all legacy pages that already have active chunks. This prevents the 5-minute reconcile task from launching an immediate indexing storm on deploy.
  - Full re-indexing of legacy cross-page chunks is managed via a dedicated throttled management command: `python manage.py reindex_legacy_chunks --throttle=1.0`.
- **Workflow Decision on Enrichment:**
  - *Enrichment is started strictly by the student's explicit "Generate enrichment" action, not automatically on approval.*
- **Document Readiness for Enrichment:**
  - A document is "ready for enrichment" if and only if:
    1. At least one page in the document is approved (`document.pages.filter(is_approved=True).exists()`).
    2. Every page is either approved or explicitly ignored (`not document.pages.filter(is_approved=False, is_ignored=False).exists()`). A document where all pages are ignored is **not** ready.
- **Ignore & Un-Ignore Semantics (No Ambiguous State):**
  - `POST /api/v1/documents/{document_id}/pages/{page_id}/ignore`:
    - Sets `is_ignored = True`.
    - Clears approval: `is_approved = False`, `approved_at = None`, `approved_by = None`, `indexed_text_hash = ""`.
    - Calls `sync_page_approval_and_indexing(document, page)`, which deactivates its chunks in pgvector and resyncs descriptor.
  - `POST /api/v1/documents/{document_id}/pages/{page_id}/unignore`:
    - Sets `is_ignored = False`, `is_approved = False`.
    - If `page.current_revision is not None`: sets `review_status = PENDING_REVIEW`.
    - If `page.current_revision is None`: leaves `review_status = PENDING_REVIEW` and `ocr_status = 'failed'` (approval blocked by check 3 until manual transcription).
    - Resyncs workflow state.
  - A page is never simultaneously `is_ignored=True` and `is_approved=True`.

---

### 2.3 Editing and Line Identity

#### 2.3.1 Model & Three-Step Non-Destructive Migration
Each revision creates new `DocumentLine` rows; `lineage_id` provides the stable identity across revisions that PR 2 references.

Fields added to `DocumentLine` (`backend/apps/documents/models.py`):
```python
lineage_id = models.UUIDField(db_index=True)  # Carried across edits; new for user-added lines.
original_text = models.TextField(blank=True, default="")  # Carried forward from the first OCR line of the lineage.
is_edited = models.BooleanField(default=False)
is_user_added = models.BooleanField(default=False)
parent_line_id = models.UUIDField(null=True, blank=True)
```
Fields added to `DocumentPageRevision` (`backend/apps/documents/models.py`):
```python
parent_revision = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='derived_revisions')
revision_type = models.CharField(max_length=20, default='ocr', choices=[('ocr', 'OCR'), ('user_edit', 'User Edit')])
created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_revisions')
review_reasons = models.JSONField(default=list, blank=True)
text_hash = models.CharField(max_length=64, blank=True, default="")  # Stored sha256("\n".join(lines))
```
Fields added to `DocumentPage` (`backend/apps/documents/models.py`):
```python
is_ignored = models.BooleanField(default=False)
ocr_attempt_count = models.PositiveIntegerField(default=0)
ocr_generation = models.PositiveIntegerField(default=0)  # Token incremented on dispatch, watchdog reap, and manual fail recovery
ocr_started_at = models.DateTimeField(null=True, blank=True)  # Timestamp set at pending/processing dispatch
index_epoch = models.PositiveIntegerField(default=0)  # Incremented on sync to ensure fresh job identity
indexed_text_hash = models.CharField(max_length=64, blank=True, default="")
```
Constraints:
- `DocumentPageRevision.Meta`: `UniqueConstraint(fields=("page", "revision_number"), name="uniq_page_revision_number")` (existing in models.py line 134)
- `DocumentLine.Meta`: `UniqueConstraint(fields=("page_revision", "lineage_id"), name="uniq_revision_lineage_id")`

**Three-Step PostgreSQL-Safe Migration:**
- `0009_transcript_schema_nullable.py`:
  - `dependencies = [('documents', '0008_documentpage_approved_at_documentpage_approved_by_and_more')]`
  - Adds `lineage_id` (nullable UUID), `original_text` (nullable TextField), `parent_line_id` (nullable UUID) to `DocumentLine`.
  - Adds `is_edited = False`, `is_user_added = False` to `DocumentLine` with non-null defaults directly (cheap metadata update on PostgreSQL 11+).
  - Adds `parent_revision` (nullable ForeignKey), `created_by` (nullable ForeignKey), `review_reasons` (default list), `revision_type = 'ocr'` (non-null default), and `text_hash = ""` (non-null default) to `DocumentPageRevision`.
  - Adds `is_ignored = False`, `ocr_attempt_count = 0`, `ocr_generation = 0`, `index_epoch = 0`, `indexed_text_hash = ""` (non-null defaults), and `ocr_started_at` (nullable DateTime) to `DocumentPage`.
- `0010_transcript_data_backfill.py`:
  - `atomic = False` (avoids monolithic transaction lock during batch operations).
  - `dependencies = [('documents', '0009_transcript_schema_nullable'), ('ai_classroom', '0004_enrichednote_empty_reason')]`
  - `RunPython` with documented reverse function (`migrations.RunPython.noop`).
  - Batch size: 500 rows.
  - **Backfill `revision_type`:** Identify pre-existing user edits via `content_snapshot__origin='user_edit'` or `edited_by__isnull=False`; set `revision_type = 'user_edit'`. Log the counts of updated user-edit vs OCR revisions.
  - **Backfill `lineage_id`:** Assign unique `uuid.uuid4()` to each existing `DocumentLine` row.
  - **Backfill `original_text`:** Set `original_text = text` (best-effort; lineage starts at migration).
  - **Backfill `text_hash`:** Compute `sha256("\n".join(lines))` inline in the migration for each existing `DocumentPageRevision`.
  - **Backfill Legacy Approval Safely (Line-Heuristics Only, No MinIO Image Calls):**
    - Pages that were already approved or user-edited (`is_approved=True` or `current_revision.revision_type='user_edit'`) stay approved.
    - Completed OCR pages are evaluated strictly using **line-based rules** (illegible line ratio > 0.15, uncertain line ratio > 0.30, repetition loop $\ge 4$, zero lines). Completed pages with no line-heuristic failures are backfilled as `is_approved=True, review_status='approved'`. Pages with any line anomaly are left as `is_approved=False, review_status='needs_review'`.
  - **Backfill `indexed_text_hash`:** For legacy pages that are approved and have active chunks, set `indexed_text_hash = current_revision.text_hash`, preventing an immediate indexing storm on deploy.
  - **Recompute Legacy Enrichment `v2:` Hashes Inline:** Compute and update `content_hash = "v2:" + sha256(...)` inline (without importing application models or methods) for all existing `EnrichedNote` instances whose source pages are approved.
  - **Defensive Check:** Log info confirming no duplicate `(page, revision_number)` exists.
- `0011_transcript_constraints_and_not_null.py`:
  - `dependencies = [('documents', '0010_transcript_data_backfill')]`
  - Alters `DocumentLine.lineage_id` to `models.UUIDField(null=False, db_index=True)`.
  - Alters `DocumentLine.original_text` to `models.TextField(blank=True, default="")`.
  - Adds `UniqueConstraint(fields=("page_revision", "lineage_id"), name="uniq_revision_lineage_id")` on `DocumentLine`.

#### 2.3.2 Edit Payload & Deterministic Validation
- **Endpoint:** `POST /api/v1/documents/{document_id}/pages/{page_id}/revisions`
- **Request Payload:**
  ```json
  {
    "expected_revision_number": 2,
    "lines": [
      {
        "lineage_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "line_index": 0,
        "text": "    def solve(n):",
        "bbox": null
      },
      {
        "lineage_id": null,
        "line_index": 1,
        "text": "        return n * 2",
        "bbox": [10.0, 20.0, 100.0, 30.0]
      }
    ]
  }
  ```
- **Order of Checks on Edit:**
  1. **In-Flight OCR Check (409):** If `page.ocr_status in ['pending', 'processing']`, return `HTTP 409 Conflict` ("OCR is currently in progress").
  2. **Ignored Page Check (422):** If `page.is_ignored == True`, return `HTTP 422 Unprocessable Content` ("Page is ignored; un-ignore before editing").
  3. **Stale Revision Check (409):** Let `current_rev = page.current_revision.revision_number if page.current_revision else 0`. If `expected_revision_number != current_rev`, return `HTTP 409 Conflict` with `latest_revision` in body.
  4. **Validation Rules (422):**
     - A provided `lineage_id` must belong to the page's current revision; otherwise return 422.
     - Duplicate `lineage_id` values in one payload return 422.
     - `line_index` values must be unique and strictly contiguous from `0` to `len(lines) - 1`; otherwise return 422.
     - Empty text (`text.strip() == ""`) returns 422. Deletion is expressed by omitting the line from the array.
     - **Preserve Code Indentation:** Do not strip leading spaces. Store text as sent (`text.rstrip("\r\n")`) so Python/code indentation survives.
     - **Server-Controlled Bounding Boxes:** For lines with an existing `lineage_id`, ignore client-sent `bbox` and copy it forward from the lineage. Accept client-sent `bbox` only for user-added lines (`lineage_id is null`), or none.
     - Maximum line length: max 1,000 characters per line.
     - Maximum lines per page: max 500 lines per page.
     - `original_text` always carries forward from the first OCR line of the lineage. User-added lines receive a new `lineage_id`, `is_user_added = True`, and `original_text = ""`.
     - Editing a line clears its uncertain flag; `is_edited = True` if text differs from `original_text` or line was modified.

#### 2.3.3 Locking & No-Op Saves
Inside `transaction.atomic()`:
1. `page = DocumentPage.objects.select_for_update().get(pk=page_id)`.
2. Perform in-flight OCR check, ignored check, and revision check (treating missing revision as 0).
3. **No-Op Save Detection:** Compare submitted lines with current revision lines (exact text, order, and `lineage_id`). If identical, return `HTTP 200 OK` with the current revision, creating no new revision and enqueuing no jobs.
4. **Edit on `ocr_failed` without revision:** If `page.current_revision is None`, allow manual transcription with `expected_revision_number = 0` (or `null`), creating Revision 1, setting `ocr_status = 'failed'`, transitioning `review_status = PENDING_REVIEW`, and bumping `ocr_generation`.

#### 2.3.4 Editing Approved Transcripts
Editing an approved page keeps it approved (`is_approved = True`, `review_status = APPROVED`). It creates a new revision, increments `page.index_epoch += 1`, calls `sync_page_approval_and_indexing(document, page)` which triggers per-page incremental re-indexing, updates `_descriptor(document)`, and invalidates downstream enrichment staleness.

---

### 2.4 State Machine & Concurrency Invariants

| State Combination (`ocr_status` / `review_status`) | Next Allowed Transition | Edits (`POST /revisions`) | Approval (`POST /approve`) | Retry OCR (`POST /retry-ocr`) |
| :--- | :--- | :--- | :--- | :--- |
| `ocr_pending` / any | `ocr_processing`, `ocr_failed` | **409 Conflict** | **409 Conflict** | **409 Conflict** |
| `ocr_processing` / any | `needs_review`, `pending_review`, `ocr_failed` | **409 Conflict** | **409 Conflict** | **409 Conflict** |
| `ocr_failed` / `pending_review` (no revision) | `ocr_pending` (retry), `pending_review` (manual edit) | Allowed (creates rev 1 with exp_rev=0) | **422 Unprocessable (check 3: no text)** | Allowed (if attempt cap < 3) |
| `ocr_failed` / `pending_review` (has revision) | `approved` (via approve), `ocr_pending` (retry) | Allowed (creates rev 2+, stays pending) | Allowed (transitions to approved) | Allowed (requires force=true)|
| `completed` / `needs_review` | `approved` (strictly via approve) | Allowed (status unchanged) | Allowed (transitions to approved) | Allowed (force=true if user_edit)|
| `completed` / `pending_review` | `approved` (strictly via approve) | Allowed (status unchanged) | Allowed (transitions to approved) | Allowed (force=true if user_edit)|
| `completed` / `approved` | `pending_review` (via reopen) | Allowed (stays approved) | **200 OK (Idempotent No-op)** | **409 Conflict (reopen first)** |
| any / `ignored` (`is_ignored=True`) | un-ignored (via unignore) | **422 Unprocessable (un-ignore first)** | **422 Unprocessable (un-ignore first)** | **422 Unprocessable (un-ignore first)** |

- **Reopen Action:** `POST /api/v1/documents/{document_id}/pages/{page_id}/reopen` moves `approved` back to `pending_review` (`is_approved = False`), deactivates all covering chunks in pgvector, marks active enrichment stale, and resyncs descriptor.
- **Stuck OCR Watchdog:**
  - Celery beat periodic task `reap_stuck_ocr_pages_task` runs every 5 minutes.
  - Queries pages stuck in `ocr_pending` where `now - ocr_started_at > 30 minutes` (`OCR_PENDING_TIMEOUT = 1800s`).
  - Queries pages stuck in `ocr_processing` where `now - ocr_started_at > 10 minutes` (`OCR_PROCESSING_TIMEOUT = 600s`).
  - Transitions stuck pages to `ocr_status = 'failed'` with error message `"OCR timeout"`.
  - Increments `ocr_generation`, unlocking the page so the student can edit or retry.
- **OCR Generation Token Invariant:**
  - `page.ocr_generation` is incremented on:
    1. User-initiated OCR dispatch (`run_ocr_job` initial or retry).
    2. Watchdog reaping (`reap_stuck_ocr_pages_task`).
    3. Manual transcription on a failed page.
  - Celery worker receives `generation_token = page.ocr_generation`.
  - Inside `transaction.atomic()` with `select_for_update()`: worker verifies `page.ocr_generation == generation_token`.
  - If a worker was reaped by the watchdog or superseded, `token != page.ocr_generation`. The late worker safely discards its results, leaving newer revisions and state intact.
- **OCR Attempt Counting Rules:**
  - `ocr_attempt_count` is incremented **only** on user-initiated dispatch (the initial page creation/canvas finalize and manual `POST /retry-ocr`).
  - Automatic Celery infrastructure retries (e.g. broker blips) and watchdog timeouts do **not** increment `ocr_attempt_count`.

---

### 2.5 OCR Retry Strategy, Fixed Ladder & Attempt Cap
- **Endpoint:** `POST /api/v1/documents/{document_id}/pages/{page_id}/retry-ocr`
- **Attempt Cap:** `MAX_OCR_ATTEMPTS = 3` (counts initial run + up to 2 retries). Tracked on `page.ocr_attempt_count`. If `page.ocr_attempt_count >= MAX_OCR_ATTEMPTS`, returns `HTTP 422`.
- **Approved Page Guard:** Reject with `HTTP 409 Conflict` if the page is currently approved (`review_status == APPROVED`). The student must explicitly reopen the page first.
- **User-Edit Conflict Guard:** Reject with `HTTP 409 Conflict` if `current_revision.revision_type == 'user_edit'`, unless `force=true` is passed.
- **Frontend Warning on Force:** UI modal warns the student: *"Re-running OCR will replace your manual transcript edits in the active view. Older edits will remain preserved in revision history."*
- **Fixed Preprocessing Ladder:**
  - **Attempt 1:** Standard rendering and OCR recognition.
  - **Attempt 2:** High-resolution render (300 DPI / 1.5x scale).
  - **Attempt 3:** Page split into two overlapping vertical halves (top/bottom) and stitched.
- **Line Identity on Retry:** A retry result receives **brand new `lineage_id`s**. Lines from a previous user edit remain preserved in their respective older revisions.

---

### 2.6 Shared Workflow Sync, Incremental Indexing & Hash Descriptors
- **Shared Synchronization Helper:**
  `sync_page_approval_and_indexing(document, page)` is the single authoritative helper called by `approve_page`, `create_user_revision`, `reopen_page`, `ignore_page`, and `unignore_page`:
  1. Computes new descriptor: `new_hash = _descriptor(document)`.
  2. Compares with active `EnrichedNote` instances:
     `EnrichedNote.objects.filter(document=document, superseded=False).exclude(content_hash=new_hash).update(ai_stale=True)`.
  3. If page is approved and not ignored:
     - Enqueues page indexing inside `transaction.on_commit`:
       `enqueue_page_index_job(page)` with dedupe key `index_page:{page.pk}:{page.current_revision_id}:{page.index_epoch}:{_model_version()}`.
  4. If page was reopened or ignored:
     - Deactivates all chunks covering this page (including legacy cross-page chunks):
       `NoteChunk.objects.filter(document=document, page_start__lte=page.page_number, page_end__gte=page.page_number, stale=False).update(stale=True)`.
     - Clears `page.indexed_text_hash = ""`.
- **Page-Bounded Chunking & Deletion Swap (Zero Collision Guarantee):**
  - Chunks are built per page and **never cross page boundaries**.
  - `chunk_index` is deterministically computed as `page.page_number * 10000 + idx`.
  - Inside the atomic page indexing transaction:
    1. Read existing chunks covering this page (active or stale, legacy or page-bounded) to map `(content_hash -> (embedding, embedding_model, embedding_version))`.
    2. **Delete all chunk rows covering this page:**
       `NoteChunk.objects.filter(document=document, page_start__lte=page.page_number, page_end__gte=page.page_number).delete()`.
       *(This cleans up legacy cross-page chunks and ensures zero index collisions on `(document, chunk_index)` or `(revision_id, content_hash, chunk_index)`).*
    3. Insert the newly generated chunk rows, reusing embeddings from unchanged hashes or embedding new/modified chunks.
    4. Sets `page.indexed_text_hash = page.current_revision.text_hash`.
  - Editing Page 2 may re-embed Page 2's chunks, but **Page 1's vectors are 100% untouched with 0 embedding calls**.
- **Exact Hash Definitions:**
  - **`text_hash` (per revision, stored on `DocumentPageRevision`):**
    `sha256("\n".join(l.text for l in revision.lines.order_by("line_index")))`.
  - **`_descriptor(document)` (per document, string with `v2:` prefix):**
    `"v2:" + sha256("|".join(f"{p.page_number}:{l.line_index}:{l.text}" for p in document.pages.filter(is_approved=True, is_ignored=False).order_by("page_number") for l in p.current_revision.lines.order_by("line_index")))` (returns `""` if zero approved pages).
  - Reordering lines changes both `text_hash` and `_descriptor`.
- **Enrichment Concurrency Race Guard:**
  - `run_enrichment_job` records `start_hash = _descriptor(document)` when starting.
  - Persists `EnrichedNote` with `content_hash = start_hash`.
  - Computes `end_hash = _descriptor(document)`. If `end_hash != start_hash`, immediately updates `ai_stale = True`.
- **Enrichment Readiness Enforcement & Gating:**
  - Both `POST /documents/{id}/enrich` and `run_enrichment_job` enforce readiness:
    - Reject with `HTTP 422 Unprocessable Content` (error code: `NOT_READY_FOR_ENRICHMENT`) if any page is unapproved and unignored, or if the document has 0 approved pages.
  - `DocumentSerializer` exposes `ready_for_enrichment: bool` and `blocking_pages: list[int]`.
  - **Frontend Gating (`EnrichedView.tsx`):**
    - The bulk-approve bypass button is removed.
    - Automated enrichment triggers are completely disabled when `!document.ready_for_enrichment`.
    - Generate / Regenerate button is disabled with a tooltip explaining that unapproved pages must be reviewed and approved (or ignored) first.

---

## 3. File Table

| File Path (Relative) | Change Scope |
| :--- | :--- |
| `backend/apps/documents/models.py` | Add fields to `DocumentLine` (`lineage_id`, `original_text`, `is_edited`, `is_user_added`, `parent_line_id`), `DocumentPageRevision` (`parent_revision`, `revision_type`, `created_by`, `review_reasons`, `text_hash`), and `DocumentPage` (`is_ignored`, `ocr_attempt_count`, `ocr_generation`, `ocr_started_at`, `index_epoch`, `indexed_text_hash`). Add `UniqueConstraint(page_revision, lineage_id)`. |
| `backend/apps/documents/migrations/0009_transcript_schema_nullable.py` | Migration 1: add schema fields (nullable UUID/ForeignKey/DateTime fields; non-null booleans/chars/integers with defaults). |
| `backend/apps/documents/migrations/0010_transcript_data_backfill.py` | Migration 2: non-atomic (`atomic = False`) `RunPython` batch backfill of `lineage_id`, `original_text`, `revision_type`, `text_hash`, line-heuristic legacy approvals, `indexed_text_hash`, and inline `v2:` enrichment hashes. Documented no-op reverse function. |
| `backend/apps/documents/migrations/0011_transcript_constraints_and_not_null.py` | Migration 3: alter fields to NOT NULL and add `UniqueConstraint(page_revision, lineage_id)`. |
| `backend/apps/documents/validation.py` | Validation module implementing `compute_image_metrics(image_bytes)` and `evaluate_page_review_status(lines, metrics, source_type)`. Placeholders marked to calibrate on real handwritten pages before merge. |
| `backend/apps/documents/services.py` | Implement `sync_page_approval_and_indexing`. Update `approve_page` with revision check, blank page check, and conditional update. Update `create_user_revision` with `select_for_update()`, 409 conflict, no-op save detection, and `lineage_id` propagation. Update `retry_page_ocr` with fixed ladder, attempt cap, and `force` guard. Add `reopen_page`, `ignore_page`, `unignore_page`. Update `run_ocr_job` to use `validation.py`, `ocr_generation` check, `ocr_started_at`, and `SoftTimeLimitExceeded` handling. |
| `backend/apps/documents/management/commands/reindex_legacy_chunks.py` | Dedicated throttled management command to reindex legacy cross-page chunks under the page-bounded scheme safely without load spikes. |
| `backend/apps/documents/serializers.py` | Update `RevisionCreateSerializer` to accept `expected_revision_number` and lines with `lineage_id`. Update `DocumentLineSerializer` with server-controlled bbox logic and no-leading-space-trimming. Update `DocumentPageRevisionSerializer`, `DocumentPageSerializer`, and `DocumentSerializer` (`ready_for_enrichment`, `blocking_pages`). |
| `backend/apps/documents/views.py` | Configure `DocumentPageApproveView`, `DocumentPageRetryOcrView`, `DocumentPageReopenView`, `DocumentPageIgnoreView`, `DocumentPageUnignoreView`, and `create_revision` on `DocumentViewSet`. |
| `backend/apps/documents/urls.py` | Configure routes: `/pages/{page_id}/approve`, `/pages/{page_id}/retry-ocr`, `/pages/{page_id}/reopen`, `/pages/{page_id}/ignore`, `/pages/{page_id}/unignore`, and `/pages/{page_id}/revisions`. |
| `backend/apps/retrieval/services.py` | Update `build_chunks` to chunk per page strictly without crossing page boundaries, filtering only approved pages. Implement per-page indexing with `index_epoch` dedupe key, `page_number * 10000 + idx` chunk indices, and chunk deletion swap covering all covering chunks. |
| `backend/apps/ai_classroom/services.py` | Update `_descriptor(document)` to hash ordered `(page_number, line_index, text)` of approved pages only with `v2:` prefix. Enforce document readiness in `enqueue_enrichment` and `run_enrichment_job`. Add `start_hash` vs `end_hash` comparison. |
| `backend/apps/jobs/tasks.py` | Add Celery tasks: `reconcile_unindexed_pages_task` and `reap_stuck_ocr_pages_task`. |
| `backend/config/celery.py` | Add Celery beat schedule for `reconcile_unindexed_pages_task` and `reap_stuck_ocr_pages_task`. |
| `backend/config/settings/base.py` | Add `MAX_OCR_ATTEMPTS = 3`, `OCR_ILLEGIBLE_THRESHOLD = 0.15`, `OCR_UNCERTAIN_THRESHOLD = 0.30`, `OCR_LINE_UNCERTAIN_THRESHOLD = 0.80`, `OCR_PENDING_TIMEOUT = 1800`, `OCR_PROCESSING_TIMEOUT = 600`, max line length 1000, max lines per page 500, Celery soft time limit 540s. |
| `frontend/src/components/notes/HandwrittenView.tsx` | In `TranscriptPanel`: pass `expected_revision_number` and `lineage_id`, render visual chips for review reasons and uncertain/illegible lines, handle HTTP 409 by keeping unsaved draft in local state and offering "Reload latest revision" with visible diff/copy, support `force` retry warning modal, support ignore/unignore. |
| `frontend/src/components/notes/EnrichedView.tsx` | Remove bulk-approve bypass button, gate auto-generation behind document readiness, render disabled Generate button with tooltip and blocking pages when not ready. |
| `frontend/src/services/api/documents.ts` | Update `submitEdit`, `approvePage`, `retryPageOcr`, and add `reopenPage`, `ignorePage`, `unignorePage`. |
| `backend/tests/api/test_transcript_review_gate.py` | Comprehensive test suite covering all PR 1 criteria and concurrency/migration invariants. |

---

## 4. Test & Verification Plan for PR 1

The following automated tests will be authored and executed:

- [ ] **OCR completion enqueues 0 downstream jobs:** `run_ocr_job` completes without dispatching index or enrich jobs.
- [ ] **Two concurrent approvals produce exactly one index job:** Concurrent approval requests for the same page trigger exactly one index task.
- [ ] **Approval with stale expected revision returns 409:** Submitting approval with outdated `expected_revision_number` returns `HTTP 409 Conflict`.
- [ ] **Approving twice creates one job:** Conditional update short-circuits on 2nd approval, producing no new jobs.
- [ ] **Indexing happens only for approved pages:** Unapproved pages produce 0 chunks in pgvector.
- [ ] **A line keeps its lineage_id and original_text across three consecutive edits:** Stable lineage tracking across multiple user revisions.
- [ ] **Add, delete and reorder lines each persist correctly:** Add generates new `lineage_id`, delete omits row, reorder updates `line_index`.
- [ ] **Older revisions are never modified:** Previous `DocumentPageRevision` and `DocumentLine` rows are completely immutable.
- [ ] **Unknown, duplicate lineage_id, non-contiguous index, and empty text return 422:** Strict input validation enforced.
- [ ] **Max line length (1000) and max 500 lines return 422:** Boundary limits enforced.
- [ ] **Server-controlled bbox:** Client bbox ignored for existing lines and copied from lineage; accepted only for user-added lines.
- [ ] **Reorder-only save creates a new revision and changes descriptor:** Text unchanged but order changed updates `_descriptor`.
- [ ] **Code indentation preserved:** Leading spaces on lines are not stripped (`text.rstrip("\r\n")`).
- [ ] **No-op saves:** Submitting identical text/order/lineage returns 200 without creating a new revision or job.
- [ ] **Ignore, reopen and un-ignore:** Chunks deactivated (`stale=True`), `ai_stale` set, document readiness recomputed.
- [ ] **Enrichment endpoint rejects not-ready document and all-ignored document:** Returns 422 with `NOT_READY_FOR_ENRICHMENT`.
- [ ] **Legacy backfill:** Legacy `needs_review` pages are NOT auto-approved; only clean completed pages are approved.
- [ ] **Legacy reindex throttled:** Legacy documents are reindexed throttled, with old cross-page chunks deactivated.
- [ ] **Legacy enrichments get recomputed v2: hash:** Existing enrichments do not get falsely marked stale on first sync.
- [ ] **Revert edit pattern A -> B -> A:** Ends with chunks that match A without being blocked by stale idempotency key.
- [ ] **Approve, reopen, approve again ends with chunks present:** Verified via `index_epoch` incrementing.
- [ ] **Editing a page after a legacy cross-page chunk leaves no stale text searchable:** All covering chunks cleanly removed during swap.
- [ ] **Reopen then approve does not collide on chunk_index with deactivated rows:** Chunks deleted during swap transaction before re-insert.
- [ ] **Watchdog reaps stuck worker:** A worker reaped by the watchdog finishes later and its result is safely discarded via `ocr_generation`.
- [ ] **A retry on an old page is not reaped:** Handled cleanly without `created_at` fallback; long-queued pending page is governed by `OCR_PENDING_TIMEOUT` (30m).
- [ ] **Attempt cap counts only user actions:** Celery auto-retries and watchdog timeouts do not consume OCR attempts.
- [ ] **The 0010 migration touches no image storage (MinIO) and runs without importing app code:** Pure line heuristics and inline hashing.
- [ ] **Failed page with a manual revision:** Approve works, retry requires `force=true`.
- [ ] **Approving a zero-line page returns 422:** Rejects blank transcripts with informative message.
- [ ] **Frontend: readiness gating and auto-trigger:** Generate button disabled when document is not ready; auto-trigger suppressed.
- [ ] **Migration nullability verified:** `is_edited`, `is_user_added`, `revision_type` are NOT NULL after migration.
- [ ] **Edit and approve on page with no revision:** Missing revision treated as 0 without crashing.
- [ ] **Retry rejected on approved page unless reopened:** Returns 409 Conflict on approved page until `reopen` is called.
- [ ] **Retry rejected after user edit unless force=true:** Rejection on user edits without force; allowed when `force=true`.
- [ ] **A fourth OCR attempt returns 422:** `MAX_OCR_ATTEMPTS = 3` cap strictly enforced via `ocr_attempt_count`.
- [ ] **Retry during pending OCR and edit during pending OCR return 409:** Race protection while OCR is in-flight.
- [ ] **NEEDS_REVIEW heuristics derived correctly:** Illegible-heavy, uncertain-heavy, repeated-line, and blank pages flagged with exact `review_reasons`.
- [ ] **Editing an approved page keeps it approved, queues exactly one index job, and sets ai_stale:** Status invariant preserved.
- [ ] **Incremental indexing page-boundary isolation:** Editing Page 2 re-embeds Page 2 chunks; Page 1 vectors remain 100% untouched with 0 embedding calls.
- [ ] **Two index jobs for pages of one document run concurrently with no chunk collision:** Collision-free indexing via page-offset chunk numbering.
- [ ] **_descriptor excludes unapproved and ignored pages:** Content hash changes only when approved page text changes.
- [ ] **Concurrent enrichment and edit sets ai_stale immediately:** Start vs end hash mismatch caught at persistence boundary.
- [ ] **Duplicate Celery delivery does not corrupt state:** Re-delivered OCR or index task is safely idempotent.
- [ ] **RLS profile isolation:** A profile cannot read, edit, approve, or retry another profile's pages.
- [ ] **Three-step migration runs on PostgreSQL without pending trigger event errors:** Schema nullable, non-atomic RunPython batch backfill with reverse, alter not-null & constraints.
- [ ] **Frontend 409 conflict handling:** 409 retains the student's unsaved draft in local state and offers reload with diff.

---

## 5. Definition of Done for PR 1

PR 1 is complete when:
- Line identity (`lineage_id`) and `original_text` survive multiple revisions.
- OCR completion never indexes or enriches before approval.
- Approval uses conditional updates with `expected_revision_number` and is completely idempotent.
- Editing an approved page keeps it approved, triggers incremental per-page indexing, and invalidates downstream enrichment staleness.
- Retry cap (3), fixed preprocessing ladder, stuck OCR watchdog, and in-flight OCR state guards are strictly enforced.
- The 3-step migration runs cleanly on PostgreSQL, touches no MinIO storage, correctly backfills `v2:` hashes and legacy approvals without indexing storms, and is fully reversible.
- The frontend review screen (`TranscriptPanel` in `HandwrittenView.tsx`) works end to end (edit, approve, retry, conflict handling without losing draft text, ignore/unignore, and enrichment readiness gating).
- All new tests pass, zero regressions across the existing 641 tests, and no files are committed or pushed without user approval.
