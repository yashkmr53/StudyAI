"""Regression tests for early insufficient-content gate and enrichment lifecycle."""
from unittest.mock import patch
from django.test import TestCase

from apps.ai_classroom.models import EnrichedNote
from apps.ai_classroom.content_gate import (
    validate_text_academic_content,
    validate_note_academic_content,
)
from apps.ai_classroom.services import EnrichmentService, run_enrichment_job
from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.jobs.models import Job
from apps.profiles.models import Profile
from tests.api.utils import authenticated_client


class ContentGateClassificationTests(TestCase):
    """Deterministic classification tests for note content sufficiency."""

    def test_blank_and_whitespace_content(self):
        for raw in ["", "   ", "\n\t\n"]:
            valid, reason, _ = validate_text_academic_content(raw)
            self.assertFalse(valid)
            self.assertEqual(reason, "blank_content")

    def test_unreadable_and_noise_content(self):
        for raw in ["??", "--", "12", "..."]:
            valid, reason, _ = validate_text_academic_content(raw)
            self.assertFalse(valid)
            self.assertEqual(reason, "unreadable_content")

    def test_personal_name_insufficient_content(self):
        for raw in ["Yash Kumar", "John Doe", "Alice Smith", "Yash"]:
            valid, reason, _ = validate_text_academic_content(raw)
            self.assertFalse(valid)
            self.assertEqual(reason, "insufficient_content")

    def test_conversational_greetings_and_test_tokens(self):
        for raw in ["hello", "hi there", "good morning", "test", "asdf qwerty"]:
            valid, reason, _ = validate_text_academic_content(raw)
            self.assertFalse(valid)
            self.assertEqual(reason, "insufficient_content")

    def test_short_academic_notes_pass_gate(self):
        academic_samples = [
            "Pointers store memory addresses in C",
            "Recursion is when a function calls itself.",
            "O(n log n) time complexity for mergesort",
            "Newton's second law is F = ma",
            "Mitochondria is the powerhouse of the cell",
            "Binary search requires a sorted array and runs in logarithmic time",
        ]
        for raw in academic_samples:
            valid, reason, _ = validate_text_academic_content(raw)
            self.assertTrue(valid, f"Expected {raw} to pass gate")
            self.assertEqual(reason, "")

    def test_code_snippets_pass_gate(self):
        code_samples = [
            "int *p = &x;",
            "void swap(int *a, int *b) { int temp = *a; *a = *b; *b = temp; }",
            "struct Node { int data; struct Node *next; };",
        ]
        for raw in code_samples:
            valid, reason, _ = validate_text_academic_content(raw)
            self.assertTrue(valid, f"Expected code {raw} to pass gate")
            self.assertEqual(reason, "")


class EnrichmentInsufficientContentPipelineTests(TestCase):
    """End-to-end service and API tests for insufficient content handling and polling mitigation."""

    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc = Document.objects.create(
            profile=self.profile,
            title="Student Notes",
            source="canvas",
            source_type="canvas_page",
        )
        self.page = DocumentPage.objects.create(
            document=self.doc,
            page_number=1,
            ocr_status=DocumentPage.OcrStatus.COMPLETED,
            review_status=DocumentPage.ReviewStatus.APPROVED,
            is_approved=True,
        )

    def _create_revision_with_text(self, text: str):
        rev = DocumentPageRevision.objects.create(
            page=self.page,
            revision_number=self.page.revisions.count() + 1,
            content_hash=f"hash-{self.page.revisions.count() + 1}",
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
            content_snapshot={"lines": [{"text": text}]},
        )
        DocumentLine.objects.create(
            page_revision=rev,
            line_index=0,
            text=text,
        )
        self.page.current_revision_id = rev.pk
        self.page.ocr_status = DocumentPage.OcrStatus.COMPLETED
        self.page.review_status = DocumentPage.ReviewStatus.APPROVED
        self.page.is_approved = True
        self.page.save(update_fields=("current_revision_id", "ocr_status", "review_status", "is_approved"))
        return rev

    def test_yash_kumar_note_skips_llm_and_records_insufficient_content(self):
        """Minimal note 'Yash Kumar' triggers early gate, records empty_reason, and marks job succeeded."""
        self._create_revision_with_text("Yash Kumar")

        # Confirm gate detects insufficient content on document
        valid, reason, _ = validate_note_academic_content(self.doc)
        self.assertFalse(valid)
        self.assertEqual(reason, "insufficient_content")

        job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(self.doc.pk),
            profile_id=self.profile.pk,
            status=Job.Status.RUNNING,
        )

        with patch("ai.langgraph.graphs.enrichment_graph.invoke_enrichment_graph") as mock_graph:
            run_enrichment_job(job)
            # LLM inference / graph must NOT have been called
            mock_graph.assert_not_called()

        enriched = EnrichedNote.objects.filter(document=self.doc, superseded=False).first()
        self.assertIsNotNone(enriched)
        self.assertEqual(enriched.empty_reason, "insufficient_content")
        self.assertEqual(enriched.blocks.count(), 0)

        # API returns 200 with structured empty_reason
        resp = self.alice.get(f"/api/v1/documents/{self.doc.pk}/enrichment")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["empty_reason"], "insufficient_content")
        self.assertEqual(data["blocks"], [])

    def test_enqueue_enrichment_does_not_duplicate_job_for_existing_insufficient_result(self):
        """enqueue_enrichment re-returns existing non-stale insufficient result without queueing a new job."""
        self._create_revision_with_text("Yash Kumar")
        EnrichedNote.objects.create(
            document=self.doc,
            content_hash="some-hash",
            provider="content_gate",
            model="qwen3.5:4b",
            prompt_version="content_gate:v1",
            empty_reason="insufficient_content",
            ai_stale=False,
            superseded=False,
        )

        result = EnrichmentService.enqueue_enrichment(self.profile.user, str(self.doc.pk))
        self.assertIsNotNone(result["note"])
        self.assertIsNone(result["job"])
        self.assertEqual(result["note"].empty_reason, "insufficient_content")

    def test_updating_note_invalidates_stale_enrichment(self):
        """Creating a new revision sets ai_stale=True on previously generated enrichment."""
        from apps.documents.services import IngestionService

        self._create_revision_with_text("Yash Kumar")
        enriched = EnrichedNote.objects.create(
            document=self.doc,
            content_hash="old-hash",
            provider="content_gate",
            model="qwen3.5:4b",
            prompt_version="content_gate:v1",
            empty_reason="insufficient_content",
            ai_stale=False,
            superseded=False,
        )

        # Simulate user writing more notes and creating a new revision
        IngestionService._create_revision_locked(
            self.page,
            content_hash="new-rev-hash",
            ocr_status=DocumentPageRevision.OcrStatus.PENDING,
        )

        enriched.refresh_from_db()
        self.assertTrue(enriched.ai_stale)

        # Once user completes transcription/approval for the updated note, enqueue_enrichment enqueues a fresh job
        self.page.refresh_from_db()
        self.page.ocr_status = DocumentPage.OcrStatus.COMPLETED
        self.page.review_status = DocumentPage.ReviewStatus.APPROVED
        self.page.is_approved = True
        self.page.save(update_fields=("ocr_status", "review_status", "is_approved"))

        # After becoming stale, enqueue_enrichment enqueues a fresh job rather than returning the stale note
        result = EnrichmentService.enqueue_enrichment(self.profile.user, str(self.doc.pk))
        self.assertIsNone(result["note"])
        self.assertIsNotNone(result["job"])

    def test_foreign_user_cannot_read_or_enrich_document(self):
        """Cross-profile security: Bob cannot access or enrich Alice's document."""
        self._create_revision_with_text("Pointers in C")
        bob = authenticated_client("bob@example.com", "s3curePass!y")

        resp_get = bob.get(f"/api/v1/documents/{self.doc.pk}/enrichment")
        self.assertEqual(resp_get.status_code, 404)

        resp_post = bob.post(f"/api/v1/documents/{self.doc.pk}/enrich")
        self.assertEqual(resp_post.status_code, 404)
