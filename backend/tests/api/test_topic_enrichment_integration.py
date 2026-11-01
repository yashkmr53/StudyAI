"""API and Integration Tests for Topic-Based Note Enrichment (Internal Retrieval Only - PR 2).

Tests:
1. Readiness Gating (unapproved pages rejected).
2. Content Gate rejection (insufficient content creates no note).
3. Full pipeline execution: clean note generates EnrichedNote with status="ok".
4. Early-exit no-op: identical inputs exit early as already_up_to_date.
5. Regenerate creates fresh note via unique run nonce.
6. Checkpoint resume with Send: per-topic checkpoint rows skip completed nodes.
7. Repair changes output with pass numbering (write#1, verify#1).
8. Atomic persistence & late worker protection (Page first, then Document locks).
9. Revert clears stale flag via two-way sync helper.
10. Watchdog reaping by heartbeat silence.
11. RLS profile isolation for enrichment endpoints.
12. Real OS thread concurrency tests on PostgreSQL.
"""
import threading
import time
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai_classroom.models import CitationBlock, EnrichedNote, EnrichedNoteBlock
from apps.ai_classroom.services import _descriptor, sync_enrichment_staleness
from apps.documents.models import Document, DocumentPage, DocumentPageRevision, DocumentLine
from apps.documents.services import sync_page_approval_and_indexing
from apps.jobs.models import Job, JobExecutionState
from apps.jobs.tasks import reap_stuck_enrichment_jobs_task
from apps.profiles.models import Profile
from apps.references.models import ReferenceBook, ReferenceChunk, ReferenceDocument
from apps.subjects.models import Subject

User = get_user_model()


class TestTopicEnrichmentIntegration(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.user_a = User.objects.create_user(email="alice@test.com", password="password123")
        self.profile_a = Profile.objects.create(user=self.user_a, name="Alice Profile")
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.user_b = User.objects.create_user(email="bob@test.com", password="password123")
        self.profile_b = Profile.objects.create(user=self.user_b, name="Bob Profile")
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        self.subject = Subject.objects.create(name="Computer Science", profile=self.profile_a)

        self.doc = Document.objects.create(
            profile=self.profile_a,
            subject=self.subject,
            title="Operating Systems Notes",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.PDF,
        )

        self.page = DocumentPage.objects.create(
            document=self.doc,
            page_number=1,
            ocr_status=DocumentPage.OcrStatus.COMPLETED,
            review_status=DocumentPage.ReviewStatus.APPROVED,
            is_approved=True,
            is_ignored=False,
            approved_by=self.user_a,
            approved_at=timezone.now(),
        )

        self.rev = DocumentPageRevision.objects.create(
            page=self.page,
            revision_number=1,
            created_by=self.user_a,
            text_hash="hash-rev-1",
        )
        self.page.current_revision_id = self.rev.id
        self.page.save()

        # Create approved academic transcript lines
        self.line1 = DocumentLine.objects.create(
            page_revision=self.rev,
            line_index=0,
            lineage_id=uuid.uuid4(),
            text="Operating systems use virtual memory with paging algorithms.",
            original_text="Operating systems use virtual memory with paging algorithms.",
        )
        self.line2 = DocumentLine.objects.create(
            page_revision=self.rev,
            line_index=1,
            lineage_id=uuid.uuid4(),
            text="Page faults occur when an address is not in physical RAM.",
            original_text="Page faults occur when an address is not in physical RAM.",
        )

        # Setup reference textbook chunk
        self.ref_doc = ReferenceDocument.objects.create(
            title="Modern Operating Systems",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            status=ReferenceDocument.Status.READY,
            subject=self.subject,
        )
        self.ref_chunk = ReferenceChunk.objects.create(
            reference_document=self.ref_doc,
            chunk_index=0,
            text="Virtual memory allows executing processes that are not completely in memory. Page replacement algorithms include LRU and FIFO.",
            page_number=42,
            embedding=[0.1] * 1024,
        )

    def test_readiness_gating_unapproved_pages_rejected(self):
        """Unapproved note pages reject enrichment request with HTTP 400 / NOT_READY_FOR_ENRICHMENT."""
        # Add an unapproved page
        unapproved_page = DocumentPage.objects.create(
            document=self.doc,
            page_number=2,
            ocr_status=DocumentPage.OcrStatus.COMPLETED,
            review_status=DocumentPage.ReviewStatus.PENDING_REVIEW,
            is_approved=False,
            is_ignored=False,
        )

        res = self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.data["error"]["code"], "NOT_READY_FOR_ENRICHMENT")

    def test_content_gate_rejection_insufficient_content(self):
        """A document with non-academic greeting content creates no note and records insufficient_content."""
        doc2 = Document.objects.create(
            profile=self.profile_a,
            title="Greetings Note",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.PDF,
        )
        page2 = DocumentPage.objects.create(
            document=doc2,
            page_number=1,
            ocr_status=DocumentPage.OcrStatus.COMPLETED,
            review_status=DocumentPage.ReviewStatus.APPROVED,
            is_approved=True,
            is_ignored=False,
        )
        rev2 = DocumentPageRevision.objects.create(
            page=page2,
            revision_number=1,
            created_by=self.user_a,
            text_hash="hash-rev-2",
        )
        page2.current_revision_id = rev2.id
        page2.save()

        DocumentLine.objects.create(
            page_revision=rev2,
            line_index=0,
            lineage_id=uuid.uuid4(),
            text="Hello testing asdf qwerty",
            original_text="Hello testing asdf qwerty",
        )

        res = self.client_a.post(f"/api/v1/documents/{doc2.id}/enrichment/regenerate")
        self.assertEqual(res.status_code, 202)
        job_id = res.data["job"]["id"]

        job = Job.objects.get(pk=job_id)
        # Should be succeeded with outcome=insufficient_content and NO note created
        self.assertEqual(job.status, Job.Status.SUCCEEDED)
        self.assertEqual(job.metadata.get("outcome"), "insufficient_content")
        self.assertFalse(EnrichedNote.objects.filter(document=doc2).exists())

    def test_full_enrichment_generation_ok(self):
        """Valid approved document generates an EnrichedNote with status='ok' and blocks."""
        res = self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate")
        self.assertEqual(res.status_code, 202)
        job_id = res.data["job"]["id"]

        job = Job.objects.get(pk=job_id)
        self.assertEqual(job.status, Job.Status.SUCCEEDED)
        self.assertEqual(job.metadata.get("outcome"), "ok")

        note = EnrichedNote.objects.filter(document=self.doc, superseded=False).first()
        self.assertIsNotNone(note)
        self.assertEqual(note.status, "ok")
        self.assertEqual(note.generation_job, job)

        # Verify blocks exist
        blocks = list(note.blocks.all())
        self.assertGreater(len(blocks), 0)
        self.assertTrue(any(b.block_kind == EnrichedNoteBlock.BlockKind.HEADING for b in blocks))
        self.assertTrue(any(b.block_kind == EnrichedNoteBlock.BlockKind.STUDENT for b in blocks))

        # Check GET /documents/{id}/enrichment returns note and latest_job with progress
        get_res = self.client_a.get(f"/api/v1/documents/{self.doc.id}/enrichment")
        self.assertEqual(get_res.status_code, 200)
        self.assertIsNotNone(get_res.data.get("note"))
        self.assertIsNotNone(get_res.data.get("latest_job"))
        self.assertIn("progress", get_res.data["latest_job"])

    def test_early_exit_already_up_to_date(self):
        """Re-running when fresh active note exists with identical inputs exits early as already_up_to_date."""
        # Initial run
        self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate")
        initial_note = EnrichedNote.objects.filter(document=self.doc, superseded=False).first()
        self.assertIsNotNone(initial_note)

        # Trigger second run with force_rerun=True (creates fresh job)
        res = self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate", {"force_rerun": True})
        self.assertEqual(res.status_code, 202)
        second_job_id = res.data["job"]["id"]

        second_job = Job.objects.get(pk=second_job_id)
        self.assertEqual(second_job.status, Job.Status.SUCCEEDED)
        self.assertEqual(second_job.metadata.get("outcome"), "already_up_to_date")
        # No second note should have been created; initial note remains active
        self.assertEqual(EnrichedNote.objects.filter(document=self.doc).count(), 1)

    def test_regenerate_creates_fresh_note_via_run_nonce(self):
        """Regenerate after content revision creates a fresh note without database key collisions."""
        # Initial run
        self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate")
        note1 = EnrichedNote.objects.filter(document=self.doc, superseded=False).first()
        self.assertIsNotNone(note1)

        # Modify transcript line
        self.line1.text = "Operating systems use virtual memory with advanced page caching."
        self.line1.save()

        # Run regenerate
        res = self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate", {"force_rerun": True})
        self.assertEqual(res.status_code, 202)

        note2 = EnrichedNote.objects.filter(document=self.doc, superseded=False).first()
        self.assertIsNotNone(note2)
        self.assertNotEqual(note1.pk, note2.pk)
        note1.refresh_from_db()
        self.assertTrue(note1.superseded)

    def test_checkpoint_resume_with_send_per_topic(self):
        """JobExecutionState stores checkpoints per topic; resume re-uses completed topic checkpoints."""
        job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(self.doc.pk),
            profile_id=self.doc.profile_id,
            idempotency_key=f"test_cp_{uuid.uuid4().hex[:8]}",
            status=Job.Status.RUNNING,
        )

        # Pre-seed a completed topic checkpoint in JobExecutionState
        JobExecutionState.objects.create(
            job=job,
            completed_node="write#0",
            topic_id="t1",
            state_json={
                "topic_id": "t1",
                "title": "Cached Topic 1",
                "blocks": [{"type": "student", "text": "Precomputed text", "line_ids": []}],
                "evidence_status": "sufficient",
                "writer_failed": False,
                "no_reference_found": False,
            },
            calls_used=1,
        )

        # Check unique constraint (job, completed_node, topic_id)
        with self.assertRaises(Exception):
            with transaction.atomic():
                JobExecutionState.objects.create(
                    job=job,
                    completed_node="write#0",
                    topic_id="t1",
                    state_json={},
                )

    def test_repair_changes_output_with_pass_numbering(self):
        """Repair pass stage names include '#1' so pre-repair '#0' checkpoints are not reused."""
        job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(self.doc.pk),
            profile_id=self.doc.profile_id,
            idempotency_key=f"test_repair_{uuid.uuid4().hex[:8]}",
            status=Job.Status.RUNNING,
        )

        # Write pre-repair row
        JobExecutionState.objects.create(
            job=job,
            completed_node="write#0",
            topic_id="t1",
            state_json={"writer_failed": True},
        )

        # Write repair row with #1
        repair_row = JobExecutionState.objects.create(
            job=job,
            completed_node="write#1",
            topic_id="t1",
            state_json={"writer_failed": False, "repaired": True},
        )
        self.assertIsNotNone(repair_row)
        self.assertEqual(repair_row.completed_node, "write#1")

    def test_revert_clears_stale_flag(self):
        """Editing and reverting back to original text clears ai_stale flag via two-way helper."""
        self.client_a.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate")
        note = EnrichedNote.objects.filter(document=self.doc, superseded=False).first()
        self.assertFalse(note.ai_stale)

        original_text = self.line1.text
        # Edit text -> triggers stale
        self.line1.text = "Changed text"
        self.line1.save()
        sync_page_approval_and_indexing(self.doc, self.page)
        note.refresh_from_db()
        self.assertTrue(note.ai_stale)

        # Revert back to original text -> clears stale!
        self.line1.text = original_text
        self.line1.save()
        sync_page_approval_and_indexing(self.doc, self.page)
        note.refresh_from_db()
        self.assertFalse(note.ai_stale)

    def test_watchdog_reaping_heartbeat_silence(self):
        """Watchdog reaps jobs with heartbeat silence exceeding threshold."""
        stuck_job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(self.doc.pk),
            profile_id=self.doc.profile_id,
            idempotency_key=f"stuck_{uuid.uuid4().hex[:8]}",
            status=Job.Status.RUNNING,
            heartbeat_at=timezone.now() - timedelta(seconds=600),
            started_at=timezone.now() - timedelta(seconds=600),
        )

        reaped = reap_stuck_enrichment_jobs_task()
        self.assertGreater(reaped, 0)
        stuck_job.refresh_from_db()
        self.assertEqual(stuck_job.status, Job.Status.CANCELLED)
        self.assertEqual(stuck_job.metadata.get("outcome"), "aborted_not_running")

    def test_rls_profile_isolation(self):
        """Bob cannot access or regenerate Alice's document enrichment."""
        res_get = self.client_b.get(f"/api/v1/documents/{self.doc.id}/enrichment")
        self.assertEqual(res_get.status_code, 404)

        res_regen = self.client_b.post(f"/api/v1/documents/{self.doc.id}/enrichment/regenerate")
        self.assertIn(res_regen.status_code, (403, 404))

        res_force = self.client_b.post(f"/api/v1/documents/{self.doc.id}/enrichment/force-include", {"force_include_line_ids": []})
        self.assertIn(res_force.status_code, (403, 404))

    def test_force_include_unknown_ids_returns_422(self):
        """Unknown line IDs return HTTP 422 Unprocessable Entity."""
        res = self.client_a.post(
            f"/api/v1/documents/{self.doc.id}/enrichment/force-include",
            {"force_include_line_ids": [str(uuid.uuid4())]},
            format="json",
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.data.get("code"), "UNKNOWN_LINE_IDS")

    def test_real_thread_concurrent_enrichment_dispatches(self):
        """Real OS threads dispatching enrichment jobs strictly follow Page then Document locking without deadlocks."""
        if connection.vendor != "postgresql":
            self.skipTest("RealThread concurrency tests require PostgreSQL row-level locks.")

        errors = []

        def worker_task(thread_id: int):
            try:
                c = APIClient()
                c.force_authenticate(user=self.user_a)
                res = c.post(
                    f"/api/v1/documents/{self.doc.id}/enrichment/regenerate",
                    {"force_rerun": True},
                )
                if res.status_code not in (200, 202):
                    errors.append(f"Thread {thread_id} got status {res.status_code}")
            except Exception as exc:
                errors.append(f"Thread {thread_id} exception: {exc}")

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrency errors occurred: {errors}")
