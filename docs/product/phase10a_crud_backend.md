# Phase 10A — CRUD Backend Foundations

**Document Version:** 1.0.0  
**Branch:** `audit/phase-10-crud`  
**Date:** September 2026  
**Implementation:** Backend & Data Model Only (Zero Frontend UI Changes)  
**Status:** Complete  

---

## 1. Executive Summary

Phase 10A implements the backend and data model foundations required for the user-facing CRUD capabilities defined in the Phase 10 audit. The core product flow (handwritten note ingestion $\to$ OCR $\to$ retrieval $\to$ gap detection $\to$ enrichment $\to$ citation verification) remains fully preserved, stable, and verified.

Key enhancements delivered in Phase 10A:
1. **Persistent Document Titling:** Added `title` (`CharField(max_length=255, default="Untitled Note")`) to the canonical `Document` model in PostgreSQL.
2. **Persistent Document-to-Notebook Association:** Added `notebook` foreign key (`ForeignKey(Notebook, on_delete=models.SET_NULL, null=True, blank=True)`) to the `Document` model.
3. **Document PATCH API:** Enabled partial mutation for `title`, `subject`, and `notebook`, enforcing strict tenant boundaries (`subject.profile == document.profile`, `notebook.profile == document.profile`, `notebook.subject == document.subject`) and protecting immutable revision, OCR, and embedding internals.
4. **Document DELETE API with Storage & Task Cleanup:** Enabled `DELETE /api/v1/documents/{id}` with complete PostgreSQL cascades, inline pgvector embedding removal, MinIO object deletion (`image_ref`, `pdf_ref`), and active Celery job cancellation/defensive worker execution.
5. **Subject DELETE API with Note Preservation:** Enabled `DELETE /api/v1/subjects/{id}`. Handled safely via `models.SET_NULL`, ensuring student study notes and folders remain intact as unfiled workspace documents.
6. **Subject PATCH Scoping:** Confirmed and hardened `PATCH /api/v1/subjects/{id}` to enforce profile isolation via `X-Active-Profile`.
7. **Chat Active-Profile Scoping Fix:** Replaced `Profile.objects.filter(user=request.user).first()` with dynamic active profile resolution (`request.profile`), isolating chat sessions and messages by active profile context.

---

## 2. Database Changes

### 2.1 Model Updates (`backend/apps/documents/models.py`)
* `Document.title`: `models.CharField(max_length=255, default="Untitled Note")`
  * Provides durable storage for note titles in PostgreSQL, replacing ephemeral IndexedDB titles.
* `Document.notebook`: `models.ForeignKey("notebooks.Notebook", on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")`
  * Links notes to notebooks/folders. When a notebook is deleted, notes are preserved with `notebook = NULL`.

### 2.2 Migration
* **Migration File:** `backend/apps/documents/migrations/0007_document_notebook_document_title.py`
* **Dependencies:** `documents.0006_alter_document_profile`, `notebooks.0002_enable_rls`
* **Application Status:** Applied to PostgreSQL test and Docker production environments (`Applying documents.0007_document_notebook_document_title... OK`).
* **Backward Compatibility:** Existing documents automatically default to `title = "Untitled Note"` and `notebook = NULL`.

---

## 3. API Changes

### 3.1 Document Endpoints (`backend/apps/documents/views.py` & `serializers.py`)
* **Allowed HTTP Methods:** Updated `DocumentViewSet.http_method_names` to:
  ```python
  http_method_names = ["get", "post", "patch", "delete", "head", "options"]
  ```
* **Active Profile Scoping:** `DocumentViewSet.get_queryset` now honors `X-Active-Profile` header and `?profile=` query param. If a document belongs to Profile A, requests using Profile B context receive HTTP 404.
* **Document Creation (`POST /api/v1/documents`):**
  * Accepts optional `title` (defaults to filename or `"Untitled Note"`) and `notebook` (UUID).
  * Validates that `notebook.profile == profile`.
  * If `notebook.subject` is set and `subject` is omitted, auto-assigns `subject = notebook.subject`.
* **Document Update (`PATCH /api/v1/documents/{id}`):**
  * Serializer: `DocumentUpdateSerializer`
  * Editable fields: `title`, `subject`, `notebook`.
  * Sanitization: Strips whitespace; blank titles fall back to `"Untitled Note"`.
  * Security validations:
    * `subject.profile == document.profile`
    * `notebook.profile == document.profile`
    * `notebook.subject == document.subject` (rejects conflicting notebook/subject assignments).
  * Immutable fields: Requests attempting to mutate `profile`, `created_at`, `source`, `source_type`, or `schema_version` are ignored.
* **Document Deletion (`DELETE /api/v1/documents/{id}`):**
  * Returns HTTP 204 No Content.
  * Subsequent GET requests return HTTP 404 Not Found.

### 3.2 Subject Endpoints (`backend/apps/subjects/views.py`)
* **Allowed HTTP Methods:** Updated `SubjectViewSet.http_method_names` to:
  ```python
  http_method_names = ["get", "post", "patch", "delete", "head", "options"]
  ```
* **Active Profile Scoping:** `SubjectViewSet.get_queryset` now supports `X-Active-Profile` header.
* **Subject Deletion (`DELETE /api/v1/subjects/{id}`):**
  * Removes subject row from database.
  * Foreign key constraints (`on_delete=models.SET_NULL`) on `Document.subject`, `Notebook.subject`, `ChatSession.subject`, `CanvasSession.subject`, and `NoteChunk.subject` ensure all student content remains intact and transitions to unfiled state.

### 3.3 Chat Endpoints (`backend/apps/chat/views.py`)
* **Active Profile Scoping:**
  * Fixed `ChatSessionViewSet.create` to use `request.profile` instead of `Profile.objects.filter(user=request.user).first()`.
  * Enforces `subject.profile == request.profile` when `subject` is provided.
  * Filters `ChatSessionViewSet.get_queryset` by `profile = request.profile` when an active profile context is present, preventing chat history leaks across profiles.

---

## 4. Deletion Cascade & Lifecycle Analysis

When `DELETE /api/v1/documents/{id}` is executed, resources are cleaned across all application tiers:

```
DELETE /api/v1/documents/{id}
 │
 ├── 1. Celery Active Job Cancellation:
 │    ├── Cancels queued/running "document" jobs (enrich, index, pdf_render)
 │    └── Cancels queued/running "ocr" jobs for document revision IDs
 │
 ├── 2. PostgreSQL Relational Cascade (atomic):
 │    ├── DocumentPage (CASCADE)
 │    │    └── DocumentPageRevision (CASCADE)
 │    │         └── DocumentLine (CASCADE)
 │    ├── NoteChunk (CASCADE)
 │    │    └── Inline 1024-dim pgvector embedding column (DELETED)
 │    ├── EnrichedNote (CASCADE)
 │    │    └── EnrichedNoteBlock (CASCADE)
 │    │         └── CitationBlock (CASCADE)
 │    ├── Question (CASCADE)
 │    └── Audit log record created (action="document.deleted")
 │
 ├── 3. MinIO Object Storage Cleanup:
 │    ├── storage.delete(page.image_ref) for all document scan images
 │    └── storage.delete(digitized.pdf_ref) for all rendered PDFs
 │
 └── 4. Worker Resilience Handlers:
      ├── run_ocr_job: catches missing revision/document, cancels job, exits safely
      ├── run_index_job: catches missing document, cancels job, exits safely
      ├── run_enrichment_job: catches missing document at start and before DB commit, exits safely
      └── render_and_store: catches missing document, cancels job, exits safely
```

---

## 5. Storage Cleanup Verification

The storage cleanup implementation in `DocumentViewSet.perform_destroy`:
1. Gathers all `image_ref` paths from `DocumentPage` records before deleting rows.
2. Gathers all `pdf_ref` paths from `DigitizedDocument` records.
3. Executes database row deletion inside an atomic transaction.
4. Invokes `get_object_storage().delete(key)` for each referenced asset.
5. Catches storage errors to prevent orphaned failures from breaking HTTP 204 responses.

Verified with unit tests using `LocalObjectStorage`: uploaded image bytes and digitized PDF artifacts are verified to exist before deletion and confirmed absent after document deletion.

---

## 6. Chat Profile Isolation Verification

* `ProfileAuthorizationService.get_active_profile` was added and exposed as a dynamic property on `Request.profile` and `HttpRequest.profile`.
* It evaluates `X-Active-Profile` header (or `?profile=` parameter), confirms the authenticated user owns the profile, and binds it to the request.
* Tests verify:
  * Creating a chat under Profile A sets `session.profile = Profile A`.
  * Creating a chat under Profile B sets `session.profile = Profile B`.
  * Listing chats under Profile A returns only Profile A sessions.
  * Listing chats under Profile B returns only Profile B sessions.
  * Attempting to associate a chat in Profile A with a subject from Profile B is rejected with HTTP 422.

---

## 7. Test Results

### 7.1 New Test Suite (`backend/tests/api/test_crud_phase10a.py`)
**24 passed in 1.71s**
* `test_create_document_persists_title_and_notebook`: PASSED
* `test_create_document_defaults_title_if_not_provided`: PASSED
* `test_create_document_rejects_cross_profile_notebook`: PASSED
* `test_patch_document_title`: PASSED
* `test_patch_document_empty_title_defaults`: PASSED
* `test_patch_document_subject_and_notebook`: PASSED
* `test_patch_document_rejects_cross_profile_subject`: PASSED
* `test_patch_document_rejects_cross_profile_notebook`: PASSED
* `test_patch_document_rejects_conflicting_notebook_subject`: PASSED
* `test_patch_document_immutable_fields_ignored`: PASSED
* `test_delete_document_success`: PASSED
* `test_delete_document_cascades_all_related_models`: PASSED
* `test_delete_document_cleans_up_minio_storage`: PASSED
* `test_delete_document_cancels_active_jobs`: PASSED
* `test_worker_safety_on_deleted_document`: PASSED
* `test_delete_document_authorization`: PASSED
* `test_delete_document_profile_isolation`: PASSED
* `test_delete_subject_preserves_notes_as_unfiled`: PASSED
* `test_delete_subject_profile_isolation`: PASSED
* `test_patch_subject_rename`: PASSED
* `test_patch_subject_profile_isolation`: PASSED
* `test_chat_creation_scoped_to_active_profile`: PASSED
* `test_chat_listing_isolated_by_active_profile`: PASSED
* `test_chat_creation_rejects_subject_from_different_profile`: PASSED

### 7.2 Full Regression Suite (`backend/tests/api/`)
**149 passed, 1 skipped in 4.80s**
* `test_ai_classroom.py`: 9/9 passed
* `test_auth_flow.py`: 6/6 passed
* `test_canvas.py`: 20/20 passed
* `test_canvas_ingestion.py`: 4/4 passed
* `test_crud_phase10a.py`: 24/24 passed
* `test_documents.py`: 19/19 passed
* `test_hardening.py`: 15/15 passed
* `test_learning_features.py`: 12/12 passed
* `test_note_space.py`: 10/10 passed
* `test_profiles_subjects.py`: 16/16 passed
* `test_retrieval.py`: 14/14 passed (1 skipped)

---

## 8. Remaining Work (Future Phases)

* **Phase 10B — Store & Frontend API Integration:**
  * Update `documentsApi` (`rename`, `remove`, `move`).
  * Wire `workspaceStore.ts` to sync note titles, folder moves, and note/subject/folder deletions with backend REST endpoints.
  * Wire folder rename and delete methods to `notebooksApi`.
* **Phase 10C — UI Action Affordances & Dialogs:**
  * Inline note title editing in `NoteDetailPage.tsx`.
  * Note card action menu (`...`) with Rename, Move to Folder, and Delete.
  * Confirmation modals for Document and Subject deletion.
  * Subject rename and delete controls in Subject Workspace.

---

PHASE 10A COMPLETE
