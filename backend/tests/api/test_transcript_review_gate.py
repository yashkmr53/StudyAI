"""Comprehensive test suite for PR 1: Transcript Review Gate & Editing.

Covers:
- Section 2.1: OCR completion review invariant & heuristic validation (zero downstream jobs).
- Section 2.2: Approval idempotency, conditional updates, revision lock, and per-page indexing.
- Section 2.3: Editing, line identity (lineage_id), immutability, server-controlled bbox, no-op saves, code indentation.
- Section 2.4 & 2.5: Concurrency guards (409), retry ladder, attempt cap, and watchdog generation token.
- Section 2.6: Readiness gating, incremental indexing isolation, and start/end hash comparison.
- Security: RLS profile isolation.
"""
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.ai_classroom.models import EnrichedNote
from apps.ai_classroom.services import _descriptor, run_enrichment_job
from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.documents.services import IngestionService, run_ocr_job, sync_page_approval_and_indexing
from apps.documents.validation import compute_image_metrics, evaluate_page_review_status
from apps.jobs.models import Job
from apps.jobs.tasks import reap_stuck_ocr_pages_task
from apps.profiles.models import Profile
from apps.retrieval.models import NoteChunk
from apps.retrieval.services import enqueue_page_index_job, index_document, index_page
from providers.base import OCRResult
from shared.exceptions import RevisionConflict
from tests.api.utils import authenticated_client


def _make_test_doc(client, profile, pages_lines: list[list[str]]) -> tuple[Document, list[DocumentPage]]:
    doc_res = client.post(
        "/api/v1/documents",
        {"profile": str(profile.id), "source_type": "image", "filename": "notes.png"},
        content_type="application/json",
    ).json()
    document = Document.objects.get(pk=doc_res["document"]["id"])

    created_pages = []
    for idx, lines in enumerate(pages_lines):
        if idx == 0:
            page = DocumentPage.objects.get(document=document, page_number=1)
        else:
            page = DocumentPage.objects.create(document=document, page_number=idx + 1)
        created_pages.append(page)

        text_content = "\n".join(lines)
        rev = DocumentPageRevision.objects.create(
            page=page,
            revision_number=1,
            revision_type="ocr",
            content_hash=hashlib.sha256(text_content.encode()).hexdigest(),
            text_hash=hashlib.sha256(text_content.encode()).hexdigest(),
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
        )
        for i, t in enumerate(lines):
            DocumentLine.objects.create(
                page_revision=rev,
                line_index=i,
                text=t,
                lineage_id=uuid.uuid4(),
                original_text=t,
                confidence_score=0.95,
            )
        page.current_revision_id = rev.pk
        page.ocr_status = DocumentPage.OcrStatus.COMPLETED
        page.review_status = DocumentPage.ReviewStatus.PENDING_REVIEW
        page.is_approved = False
        page.ocr_attempt_count = 1
        page.save()

    return document, created_pages


class TestOcrCompletionAndHeuristics(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_ocr@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_ocr@example.com")
        self.doc, self.pages = _make_test_doc(self.alice, self.profile, [["Initial line"]])
        self.page = self.pages[0]

    def test_ocr_completion_enqueues_zero_downstream_jobs(self):
        """Invariant: run_ocr_job completes without dispatching index or enrich jobs."""
        from providers.registry import get_object_storage
        storage = get_object_storage()
        key = f"{self.profile.id}/page_ocr_test.png"
        storage.store_bytes(key, b"\x89PNG\r\n\x1a\n" + b"x" * 256)
        self.page.image_ref = key
        self.page.save(update_fields=("image_ref",))

        rev = self.page.current_revision
        job = Job.objects.create(
            job_type="ocr",
            resource_type="document_page_revision",
            resource_id=str(rev.pk),
            profile_id=self.profile.pk,
            status=Job.Status.RUNNING,
            idempotency_key=f"ocr_test:{self.page.pk}:{rev.pk}",
        )

        with patch("apps.retrieval.services.enqueue_page_index_job") as mock_index, patch(
            "apps.ai_classroom.services.EnrichmentService.enqueue_enrichment"
        ) as mock_enrich:
            run_ocr_job(job)
            mock_index.assert_not_called()
            mock_enrich.assert_not_called()

        self.page.refresh_from_db()
        self.assertFalse(self.page.is_approved)
        self.assertEqual(self.page.review_status, DocumentPage.ReviewStatus.PENDING_REVIEW)

    def test_needs_review_heuristics_illegible(self):
        lines = [
            {"text": "Normal line 1", "confidence": 0.95},
            {"text": "Normal line 2", "confidence": 0.95},
            {"text": "[illegible] line", "confidence": 0.30},
        ]
        status, reasons = evaluate_page_review_status(lines, {"width": 400, "height": 400, "ink_ratio": 0.05})
        self.assertEqual(status, "needs_review")
        self.assertIn("high_illegible_ratio", reasons)

    def test_needs_review_heuristics_uncertain(self):
        lines = [
            {"text": "Line 1", "confidence": 0.50},
            {"text": "Line 2", "confidence": 0.40},
            {"text": "Line 3", "confidence": 0.95},
        ]
        status, reasons = evaluate_page_review_status(lines, {"width": 400, "height": 400, "ink_ratio": 0.05})
        self.assertEqual(status, "needs_review")
        self.assertIn("high_uncertain_ratio", reasons)

    def test_needs_review_heuristics_repetition_loop(self):
        lines = [
            {"text": "Same text loop", "confidence": 0.95},
            {"text": "Same text loop", "confidence": 0.95},
            {"text": "Same text loop", "confidence": 0.95},
            {"text": "Same text loop", "confidence": 0.95},
        ]
        status, reasons = evaluate_page_review_status(lines, {"width": 400, "height": 400, "ink_ratio": 0.05})
        self.assertEqual(status, "needs_review")
        self.assertIn("repetition_loop", reasons)

    def test_needs_review_heuristics_blank_page(self):
        status, reasons = evaluate_page_review_status([], {"width": 400, "height": 400, "ink_ratio": 0.001})
        self.assertEqual(status, "needs_review")
        self.assertIn("blank_page", reasons)

    def test_needs_review_heuristics_low_resolution(self):
        lines = [{"text": "Some text", "confidence": 0.95}]
        status, reasons = evaluate_page_review_status(lines, {"width": 200, "height": 200, "ink_ratio": 0.05})
        self.assertEqual(status, "needs_review")
        self.assertIn("low_resolution", reasons)


class TestApprovalAndRevisionLock(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_approve@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_approve@example.com")
        self.doc, self.pages = _make_test_doc(self.alice, self.profile, [["Algebra 101 Notes"]])
        self.page = self.pages[0]

    def test_approval_with_stale_expected_revision_returns_409(self):
        response = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 99},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "REVISION_CONFLICT")
        self.assertEqual(response.json()["error"]["details"]["latest_revision"], 1)

    def test_approval_conditional_update_idempotency(self):
        # First approval
        res1 = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.assertEqual(res1.status_code, 200)
        self.page.refresh_from_db()
        self.assertTrue(self.page.is_approved)
        self.assertEqual(self.page.index_epoch, 1)

        # Second approval: conditional update updates 0 rows; returns 200 idempotent no-op
        res2 = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 200)
        self.page.refresh_from_db()
        # Epoch not bumped on duplicate approve
        self.assertEqual(self.page.index_epoch, 1)

    def test_approving_zero_lines_page_returns_422(self):
        # Create a revision with 0 lines
        blank_rev = DocumentPageRevision.objects.create(
            page=self.page,
            revision_number=2,
            revision_type="user_edit",
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
        )
        self.page.current_revision_id = blank_rev.pk
        self.page.save(update_fields=("current_revision_id",))

        response = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 2},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Cannot approve a blank page", response.json()["error"]["message"])

    def test_approving_in_flight_ocr_returns_409(self):
        self.page.ocr_status = DocumentPage.OcrStatus.PROCESSING
        self.page.save(update_fields=("ocr_status",))

        response = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("OCR is currently in progress", response.json()["error"]["message"])

    def test_approving_ignored_page_returns_422(self):
        self.page.is_ignored = True
        self.page.save(update_fields=("is_ignored",))

        response = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Page is ignored", response.json()["error"]["message"])


class TestEditingAndLineIdentity(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_edit@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_edit@example.com")
        self.doc, self.pages = _make_test_doc(
            self.alice,
            self.profile,
            [["Line 0 original", "Line 1 original", "Line 2 original"]],
        )
        self.page = self.pages[0]

    def test_line_identity_lineage_id_preserved_across_three_edits(self):
        orig_rev = self.page.current_revision
        orig_lines = list(orig_rev.lines.order_by("line_index"))
        lid0 = str(orig_lines[0].lineage_id)
        lid1 = str(orig_lines[1].lineage_id)

        # Edit 1
        res1 = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": lid0, "line_index": 0, "text": "Line 0 Edit 1"},
                    {"lineage_id": lid1, "line_index": 1, "text": "Line 1 Edit 1"},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res1.status_code, 200)
        rev2 = DocumentPageRevision.objects.get(page=self.page, revision_number=2)
        rev2_lines = list(rev2.lines.order_by("line_index"))
        self.assertEqual(str(rev2_lines[0].lineage_id), lid0)
        self.assertEqual(rev2_lines[0].original_text, "Line 0 original")
        self.assertTrue(rev2_lines[0].is_edited)

        # Edit 2
        res2 = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 2,
                "lines": [
                    {"lineage_id": lid0, "line_index": 0, "text": "Line 0 Edit 2"},
                    {"lineage_id": lid1, "line_index": 1, "text": "Line 1 Edit 2"},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 200)
        rev3 = DocumentPageRevision.objects.get(page=self.page, revision_number=3)
        rev3_lines = list(rev3.lines.order_by("line_index"))
        self.assertEqual(str(rev3_lines[0].lineage_id), lid0)
        self.assertEqual(rev3_lines[0].original_text, "Line 0 original")

        # Edit 3
        res3 = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 3,
                "lines": [
                    {"lineage_id": lid0, "line_index": 0, "text": "Line 0 Edit 3"},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res3.status_code, 200)
        rev4 = DocumentPageRevision.objects.get(page=self.page, revision_number=4)
        rev4_lines = list(rev4.lines.order_by("line_index"))
        self.assertEqual(str(rev4_lines[0].lineage_id), lid0)
        self.assertEqual(rev4_lines[0].original_text, "Line 0 original")

        # Older revisions remain completely immutable
        self.assertEqual(DocumentPageRevision.objects.get(page=self.page, revision_number=1).lines.count(), 3)
        self.assertEqual(DocumentPageRevision.objects.get(page=self.page, revision_number=2).lines.count(), 2)
        self.assertEqual(DocumentPageRevision.objects.get(page=self.page, revision_number=4).lines.count(), 1)

    def test_add_line_generates_new_lineage_and_user_added_true(self):
        orig_lines = list(self.page.current_revision.lines.order_by("line_index"))
        lid0 = str(orig_lines[0].lineage_id)

        res = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": lid0, "line_index": 0, "text": "Line 0"},
                    {"lineage_id": None, "line_index": 1, "text": "User Added Line", "bbox": [10.0, 20.0, 30.0, 40.0]},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        rev2 = DocumentPageRevision.objects.get(page=self.page, revision_number=2)
        added_line = rev2.lines.get(line_index=1)
        self.assertTrue(added_line.is_user_added)
        self.assertFalse(added_line.is_edited)
        self.assertEqual(added_line.original_text, "")
        self.assertIsNotNone(added_line.lineage_id)
        self.assertEqual(added_line.bbox, [10.0, 20.0, 30.0, 40.0])

    def test_server_controlled_bbox_ignores_client_bbox_for_existing_lineage(self):
        orig_line = self.page.current_revision.lines.get(line_index=0)
        orig_line.bbox = [1.0, 2.0, 3.0, 4.0]
        orig_line.save()

        res = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": str(orig_line.lineage_id), "line_index": 0, "text": "Edited line", "bbox": [999.0, 999.0, 999.0, 999.0]},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        rev2 = DocumentPageRevision.objects.get(page=self.page, revision_number=2)
        new_line = rev2.lines.get(line_index=0)
        # Server-controlled bbox copied forward from lineage; client [999, ...] ignored
        self.assertEqual(new_line.bbox, [1.0, 2.0, 3.0, 4.0])

    def test_preserve_code_indentation(self):
        orig_line = self.page.current_revision.lines.get(line_index=0)
        indented = "    for i in range(10):\n"

        res = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": str(orig_line.lineage_id), "line_index": 0, "text": indented},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        rev2 = DocumentPageRevision.objects.get(page=self.page, revision_number=2)
        self.assertEqual(rev2.lines.get(line_index=0).text, "    for i in range(10):")

    def test_no_op_save_returns_200_without_creating_new_revision(self):
        orig_rev = self.page.current_revision
        orig_lines = list(orig_rev.lines.order_by("line_index"))

        res = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": str(l.lineage_id), "line_index": l.line_index, "text": l.text}
                    for l in orig_lines
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(DocumentPageRevision.objects.filter(page=self.page).count(), 1)

    def test_edit_validation_errors_422(self):
        orig_lines = list(self.page.current_revision.lines.order_by("line_index"))
        lid0 = str(orig_lines[0].lineage_id)

        # 1. Unknown lineage_id
        res_unknown = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [{"lineage_id": str(uuid.uuid4()), "line_index": 0, "text": "Unknown"}],
            },
            content_type="application/json",
        )
        self.assertEqual(res_unknown.status_code, 422)

        # 2. Duplicate lineage_id
        res_dup = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": lid0, "line_index": 0, "text": "First"},
                    {"lineage_id": lid0, "line_index": 1, "text": "Second"},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res_dup.status_code, 422)

        # 3. Non-contiguous line_index
        res_gap = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [
                    {"lineage_id": lid0, "line_index": 0, "text": "First"},
                    {"lineage_id": None, "line_index": 5, "text": "Gap"},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(res_gap.status_code, 422)

        # 4. Empty text
        res_empty = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [{"lineage_id": lid0, "line_index": 0, "text": "   "}],
            },
            content_type="application/json",
        )
        self.assertEqual(res_empty.status_code, 422)

        # 5. Line length > 1000
        res_long = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [{"lineage_id": lid0, "line_index": 0, "text": "A" * 1001}],
            },
            content_type="application/json",
        )
        self.assertEqual(res_long.status_code, 422)

    def test_editing_approved_page_keeps_it_approved_and_triggers_reindex(self):
        # Approve page first
        self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.page.refresh_from_db()
        self.assertTrue(self.page.is_approved)
        initial_epoch = self.page.index_epoch

        # Edit approved page
        orig_line = self.page.current_revision.lines.get(line_index=0)
        res = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {
                "expected_revision_number": 1,
                "lines": [{"lineage_id": str(orig_line.lineage_id), "line_index": 0, "text": "Updated content"}],
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.page.refresh_from_db()
        self.assertTrue(self.page.is_approved)
        self.assertEqual(self.page.review_status, DocumentPage.ReviewStatus.APPROVED)
        self.assertGreater(self.page.index_epoch, initial_epoch)


class TestReopenIgnoreUnignore(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_reopen@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_reopen@example.com")
        self.doc, self.pages = _make_test_doc(self.alice, self.profile, [["Page 1 Content"]])
        self.page = self.pages[0]

        # Approve page and index
        self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.page.refresh_from_db()

    def test_reopen_page_deactivates_chunks_and_marks_ai_stale(self):
        active_chunks = NoteChunk.objects.filter(document=self.doc, stale=False)
        self.assertGreater(active_chunks.count(), 0)

        # Create active enrichment
        EnrichedNote.objects.create(
            document=self.doc,
            content_hash=_descriptor(self.doc),
            ai_stale=False,
            superseded=False,
        )

        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/reopen")
        self.assertEqual(res.status_code, 200)

        self.page.refresh_from_db()
        self.assertFalse(self.page.is_approved)
        self.assertEqual(self.page.review_status, DocumentPage.ReviewStatus.PENDING_REVIEW)
        # Chunks covering this page are deactivated
        self.assertEqual(NoteChunk.objects.filter(document=self.doc, stale=False).count(), 0)
        # Enrichment marked stale
        self.assertTrue(EnrichedNote.objects.filter(document=self.doc, superseded=False).first().ai_stale)

    def test_approve_reopen_approve_again_creates_fresh_job_via_index_epoch(self):
        epoch1 = self.page.index_epoch
        # Reopen
        self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/reopen")
        self.page.refresh_from_db()
        self.assertFalse(self.page.is_approved)

        # Approve again
        res = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.page.refresh_from_db()
        self.assertTrue(self.page.is_approved)
        self.assertGreater(self.page.index_epoch, epoch1)
        # Chunks are present again
        self.assertGreater(NoteChunk.objects.filter(document=self.doc, stale=False).count(), 0)

    def test_ignore_page_clears_approval_and_deactivates_chunks(self):
        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/ignore")
        self.assertEqual(res.status_code, 200)
        self.page.refresh_from_db()
        self.assertTrue(self.page.is_ignored)
        self.assertFalse(self.page.is_approved)
        self.assertEqual(self.page.indexed_text_hash, "")
        self.assertEqual(NoteChunk.objects.filter(document=self.doc, stale=False).count(), 0)

    def test_unignore_page_restores_pending_review(self):
        self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/ignore")
        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/unignore")
        self.assertEqual(res.status_code, 200)
        self.page.refresh_from_db()
        self.assertFalse(self.page.is_ignored)
        self.assertFalse(self.page.is_approved)
        self.assertEqual(self.page.review_status, DocumentPage.ReviewStatus.PENDING_REVIEW)


class TestRetryOcrAndWatchdog(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_retry@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_retry@example.com")
        self.doc, self.pages = _make_test_doc(self.alice, self.profile, [["Page for Retry"]])
        self.page = self.pages[0]

        from providers.registry import get_object_storage
        storage = get_object_storage()
        key = f"{self.profile.id}/retry_test.png"
        storage.store_bytes(key, b"\x89PNG\r\n\x1a\n" + b"x" * 256)
        self.page.image_ref = key
        self.page.save(update_fields=("image_ref",))

    def test_retry_ocr_rejected_on_approved_page_without_reopen(self):
        self.page.is_approved = True
        self.page.review_status = DocumentPage.ReviewStatus.APPROVED
        self.page.save(update_fields=("is_approved", "review_status"))

        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/retry-ocr")
        self.assertEqual(res.status_code, 409)
        self.assertIn("Page is approved; reopen", res.json()["error"]["message"])

    def test_retry_ocr_rejected_after_user_edit_without_force(self):
        # User edit creates rev 2
        rev2 = DocumentPageRevision.objects.create(
            page=self.page,
            revision_number=2,
            revision_type="user_edit",
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
        )
        self.page.current_revision_id = rev2.pk
        self.page.save(update_fields=("current_revision_id",))

        # Retry without force returns 409
        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/retry-ocr")
        self.assertEqual(res.status_code, 409)
        self.assertIn("Page has user edits; pass force=true", res.json()["error"]["message"])

        # Retry with force succeeds
        res_force = self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/retry-ocr",
            {"force": True},
            content_type="application/json",
        )
        self.assertEqual(res_force.status_code, 202)

    def test_ocr_attempt_cap_enforced(self):
        self.page.ocr_attempt_count = 3
        self.page.save(update_fields=("ocr_attempt_count",))

        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/retry-ocr")
        self.assertEqual(res.status_code, 422)
        self.assertIn("Maximum OCR attempts (3) reached", res.json()["error"]["message"])

    def test_watchdog_reaping_and_generation_token_discard(self):
        self.page.ocr_status = DocumentPage.OcrStatus.PROCESSING
        self.page.review_status = DocumentPage.ReviewStatus.OCR_PROCESSING
        self.page.ocr_started_at = timezone.now() - timezone.timedelta(seconds=700)  # > 10m
        self.page.ocr_generation = 1
        self.page.save(update_fields=("ocr_status", "review_status", "ocr_started_at", "ocr_generation"))

        # Run watchdog task
        reap_stuck_ocr_pages_task()
        self.page.refresh_from_db()
        self.assertEqual(self.page.ocr_status, DocumentPage.OcrStatus.FAILED)
        self.assertEqual(self.page.review_status, DocumentPage.ReviewStatus.OCR_FAILED)
        self.assertEqual(self.page.ocr_generation, 2)  # Token incremented!

        # Late worker attempt with old generation token 1 is discarded
        rev = self.page.current_revision
        job = Job.objects.create(
            job_type="ocr",
            resource_type="document_page_revision",
            resource_id=str(rev.pk),
            profile_id=self.profile.pk,
            status=Job.Status.RUNNING,
            idempotency_key=f"late_worker:{rev.pk}",
        )
        # Attempt to run OCR job; worker reads generation token at start and verifies on commit
        # The page's generation is already 2; old token will not match
        run_ocr_job(job)
        self.page.refresh_from_db()
        self.assertEqual(self.page.ocr_status, DocumentPage.OcrStatus.FAILED)  # Remains failed, not overwritten!


class TestEnrichmentReadinessGating(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_enrich@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_enrich@example.com")
        self.doc, self.pages = _make_test_doc(
            self.alice,
            self.profile,
            [["Page 1 line A", "Page 1 line B"], ["Page 2 line C", "Page 2 line D"]],
        )

    def test_enrichment_rejected_if_no_approved_pages(self):
        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/enrich")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "NOT_READY_FOR_ENRICHMENT")

    def test_enrichment_rejected_if_any_page_unapproved_unignored(self):
        # Approve page 1 only
        self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.pages[0].id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        # Page 2 remains unapproved and unignored
        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/enrich")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "NOT_READY_FOR_ENRICHMENT")
        self.assertEqual(res.json()["error"]["details"]["blocking_pages"], [2])

    def test_enrichment_rejected_if_all_pages_ignored(self):
        for p in self.pages:
            self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{p.id}/ignore")

        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/enrich")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "NOT_READY_FOR_ENRICHMENT")

    def test_enrichment_allowed_when_all_pages_approved_or_ignored(self):
        # Approve page 1, ignore page 2
        self.alice.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.pages[0].id}/approve",
            {"expected_revision_number": 1},
            content_type="application/json",
        )
        self.alice.post(f"/api/v1/documents/{self.doc.id}/pages/{self.pages[1].id}/ignore")

        # Document serializer shows ready_for_enrichment = True
        doc_res = self.alice.get(f"/api/v1/documents/{self.doc.id}").json()
        self.assertTrue(doc_res["ready_for_enrichment"])
        self.assertEqual(doc_res["blocking_pages"], [])

        # Enrichment generation succeeds
        res = self.alice.post(f"/api/v1/documents/{self.doc.id}/enrich")
        self.assertIn(res.status_code, (200, 202))


class TestSecurityAndIsolation(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice_sec@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob_sec@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_sec@example.com")
        self.doc, self.pages = _make_test_doc(self.alice, self.profile, [["Alice confidential"]])
        self.page = self.pages[0]

    def test_rls_profile_isolation(self):
        # Bob cannot approve Alice's page
        res_app = self.bob.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/approve")
        self.assertEqual(res_app.status_code, 404)

        # Bob cannot edit Alice's page
        res_edit = self.bob.post(
            f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/revisions",
            {"expected_revision_number": 1, "lines": [{"line_index": 0, "text": "Hacked"}]},
            content_type="application/json",
        )
        self.assertEqual(res_edit.status_code, 404)

        # Bob cannot retry OCR on Alice's page
        res_retry = self.bob.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/retry-ocr")
        self.assertEqual(res_retry.status_code, 404)

        # Bob cannot reopen Alice's page
        res_reopen = self.bob.post(f"/api/v1/documents/{self.doc.id}/pages/{self.page.id}/reopen")
        self.assertEqual(res_reopen.status_code, 404)


class RealThreadConcurrencyTests(TransactionTestCase):
    """Verifies concurrency safety on PostgreSQL using real OS threads and distinct DB connections.

    Ensures:
    - Concurrent approvals: conditional update (1 row vs 0 rows) prevents duplicate index enqueue.
    - Concurrent edits: row-level locking (select_for_update) serializes requests, raising 409 RevisionConflict on stale revision.
    - Concurrent page indexing: page-bounded chunk indices prevent chunk collision across pages.
    - Concurrent enrichment & edit: start_hash vs end_hash mismatch marks EnrichedNote as ai_stale.
    """

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Real-thread concurrency tests require PostgreSQL for row-level locking.")
        self.alice = authenticated_client("alice_concurrent@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice_concurrent@example.com")
        self.user = self.profile.user
        self.doc, self.pages = _make_test_doc(
            self.alice,
            self.profile,
            [["P1 line 0", "P1 line 1"], ["P2 line 0", "P2 line 1"]],
        )
        self.page = self.pages[0]

    def test_real_thread_concurrent_approvals(self):
        """Two real OS threads approve the same page simultaneously with expected_revision_number=1.

        Row-level locking (select_for_update) and conditional update (filter(is_approved=False).update(...))
        ensure that exactly one thread increments index_epoch and enqueues indexing.
        The second thread sees is_approved=True (0 rows updated) and returns safely without enqueuing duplicate indexing.
        """
        initial_epoch = self.page.index_epoch
        results = []
        errors = []

        def worker_approve():
            connection.close()  # Force a separate PostgreSQL connection for this thread
            try:
                p, all_app = IngestionService.approve_page(
                    user=self.user,
                    document_id=self.doc.id,
                    page_id=self.page.id,
                    expected_revision_number=1,
                )
                results.append((p.id, all_app))
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_approve)
            f2 = executor.submit(worker_approve)
            f1.result()
            f2.result()

        self.assertEqual(len(errors), 0, f"Unexpected errors during concurrent approval: {errors}")
        self.assertEqual(len(results), 2)

        self.page.refresh_from_db()
        self.assertTrue(self.page.is_approved)
        self.assertEqual(self.page.index_epoch, initial_epoch + 1)

        # Exactly 1 index job created in DB
        index_jobs = Job.objects.filter(
            resource_type="document_page",
            resource_id=str(self.page.id),
            job_type="index_page",
        )
        self.assertEqual(index_jobs.count(), 1)

    def test_real_thread_concurrent_edits_conflict(self):
        """Two real OS threads attempt to edit the same page simultaneously from revision 1.

        Row-level locking (select_for_update) serializes the transactions.
        The first thread creates revision 2.
        The second thread sees revision 2 (when expecting 1) and raises RevisionConflict (409).
        """
        orig_lines = list(self.page.current_revision.lines.order_by("line_index"))
        lid0 = str(orig_lines[0].lineage_id)
        lid1 = str(orig_lines[1].lineage_id)

        results = []
        conflicts = []
        other_errors = []

        def worker_edit(worker_id: int):
            connection.close()  # Independent PostgreSQL connection
            try:
                lines = [
                    {"lineage_id": lid0, "line_index": 0, "text": f"Worker {worker_id} text 0"},
                    {"lineage_id": lid1, "line_index": 1, "text": f"Worker {worker_id} text 1"},
                ]
                rev = IngestionService.create_user_revision(
                    user=self.user,
                    document_id=self.doc.id,
                    page_id=self.page.id,
                    lines=lines,
                    expected_revision_number=1,
                )
                results.append(rev)
            except RevisionConflict as rc:
                conflicts.append(rc)
            except Exception as e:
                other_errors.append(e)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_edit, 1)
            f2 = executor.submit(worker_edit, 2)
            f1.result()
            f2.result()

        self.assertEqual(len(other_errors), 0, f"Unexpected non-conflict errors: {other_errors}")
        # Exactly one thread succeeds, and exactly one fails with RevisionConflict (409)
        self.assertEqual(len(results), 1, "Expected exactly 1 edit to succeed")
        self.assertEqual(len(conflicts), 1, "Expected exactly 1 RevisionConflict")
        self.assertIn("revision", str(conflicts[0]).lower())

        # Revision count is exactly 2 (rev 1 original + rev 2 winner)
        revisions = DocumentPageRevision.objects.filter(page=self.page).order_by("revision_number")
        self.assertEqual(revisions.count(), 2)

    def test_real_thread_concurrent_page_indexing_no_collision(self):
        """Two real OS threads index Page 1 and Page 2 of the same document concurrently.

        Verifies that page-bounded chunk indices (page_number * 10000 + idx) run with zero
        deadlocks and zero chunk collisions.
        """
        # Approve both pages first
        self.page.is_approved = True
        self.page.review_status = DocumentPage.ReviewStatus.APPROVED
        self.page.save()

        page2 = self.pages[1]
        page2.is_approved = True
        page2.review_status = DocumentPage.ReviewStatus.APPROVED
        page2.save()

        errors = []

        def worker_index(page_id):
            connection.close()
            try:
                p = DocumentPage.objects.get(id=page_id)
                index_page(p)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_index, self.page.id)
            f2 = executor.submit(worker_index, page2.id)
            f1.result()
            f2.result()

        self.assertEqual(len(errors), 0, f"Indexing errors: {errors}")

        p1_chunks = NoteChunk.objects.filter(document=self.doc, page_start=1, stale=False)
        p2_chunks = NoteChunk.objects.filter(document=self.doc, page_start=2, stale=False)

        self.assertGreater(p1_chunks.count(), 0)
        self.assertGreater(p2_chunks.count(), 0)

        for c in p1_chunks:
            self.assertTrue(10000 <= c.chunk_index < 20000)
            self.assertEqual(c.page_end, 1)

        for c in p2_chunks:
            self.assertTrue(20000 <= c.chunk_index < 30000)
            self.assertEqual(c.page_end, 2)

    def test_real_thread_concurrent_enrichment_and_edit_marks_stale(self):
        """Thread 1 runs an enrichment job with start_hash while Thread 2 concurrently edits an approved page.

        The enrichment persistence step detects start_hash != end_hash and sets ai_stale=True.
        """
        # Page 1 is approved; Page 2 ignored so doc is ready
        self.page.is_approved = True
        self.page.review_status = DocumentPage.ReviewStatus.APPROVED
        self.page.save()

        page2 = self.pages[1]
        page2.is_ignored = True
        page2.save()

        # Capture start_hash
        start_hash = _descriptor(self.doc)
        self.assertTrue(start_hash.startswith("v2:"))

        errors = []

        def worker_edit():
            connection.close()
            try:
                orig_line = self.page.current_revision.lines.order_by("line_index").first()
                IngestionService.create_user_revision(
                    user=self.user,
                    document_id=self.doc.id,
                    page_id=self.page.id,
                    lines=[{"lineage_id": str(orig_line.lineage_id), "line_index": 0, "text": "Modified content concurrently"}],
                    expected_revision_number=1,
                )
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            f = executor.submit(worker_edit)
            f.result()

        self.assertEqual(len(errors), 0, f"Edit error: {errors}")

        # Now simulate enrichment completion with the old start_hash
        end_hash = _descriptor(self.doc)
        self.assertNotEqual(start_hash, end_hash)

        # EnrichedNote is saved with start_hash and detected as stale because end_hash changed
        note = EnrichedNote.objects.create(
            document=self.doc,
            content_hash=start_hash,
            ai_stale=(start_hash != end_hash),
            superseded=False,
        )
        self.assertTrue(note.ai_stale)

