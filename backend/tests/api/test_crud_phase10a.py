"""Comprehensive tests for Phase 10A CRUD Backend Foundations.

Covers:
- Document title & notebook persistence
- Document PATCH (title, subject, notebook, validation, cross-profile rejection)
- Document DELETE (basic, cascades, MinIO cleanup, worker safety, authorization, profile isolation)
- Subject DELETE (preserves notes and notebooks via SET_NULL)
- Subject PATCH (rename, active-profile scoping, cross-profile rejection)
- Chat profile scoping (request.profile, session filtering, cross-profile rejection)
"""
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.ai_classroom.models import EnrichedNote, EnrichedNoteBlock, CitationBlock
from apps.chat.models import ChatSession
from apps.documents.models import (
    DigitizedDocument,
    Document,
    DocumentLine,
    DocumentPage,
    DocumentPageRevision,
)
from apps.documents.services import IngestionService, run_ocr_job
from apps.jobs.models import Job
from apps.notebooks.models import Notebook
from apps.profiles.models import Profile
from apps.questions.models import Question
from apps.retrieval.models import NoteChunk
from apps.retrieval.services import run_index_job
from apps.subjects.models import Subject
from providers.registry import get_object_storage
from tests.api.utils import authenticated_client


@override_settings(STORAGE_BACKEND="local")
class DocumentCrudPhase10ATests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")

        self.alice_user = User.objects.get(email="alice@example.com")
        self.bob_user = User.objects.get(email="bob@example.com")

        self.alice_profile_1 = Profile.objects.get(user=self.alice_user)
        self.alice_profile_2 = Profile.objects.create(
            user=self.alice_user,
            name="Semester 2",
            module=Profile.Module.AI_CLASSROOM,
        )

        self.bob_profile = Profile.objects.get(user=self.bob_user)

        self.subject_p1 = Subject.objects.create(
            profile=self.alice_profile_1,
            name="Data Structures",
        )
        self.subject_p2 = Subject.objects.create(
            profile=self.alice_profile_2,
            name="Algorithms",
        )

        self.notebook_p1 = Notebook.objects.create(
            profile=self.alice_profile_1,
            subject=self.subject_p1,
            title="DSA Notebook",
        )
        self.notebook_p2 = Notebook.objects.create(
            profile=self.alice_profile_2,
            subject=self.subject_p2,
            title="Algo Notebook",
        )

    def _create_doc(self, profile=None, subject=None, notebook=None, title="Lecture 1"):
        profile = profile or self.alice_profile_1
        doc, page = IngestionService.create_document(
            self.alice_user,
            profile=profile,
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
            subject=subject,
            notebook=notebook,
            title=title,
            filename="lecture.jpg",
        )
        page.image_ref = f"{profile.id}/{page.id}.png"
        page.save(update_fields=("image_ref",))
        return doc, page

    # --- 1. Document Title & Notebook Association on Create ---

    def test_create_document_persists_title_and_notebook(self):
        resp = self.alice.post(
            "/api/v1/documents",
            {
                "profile": str(self.alice_profile_1.id),
                "subject": str(self.subject_p1.id),
                "notebook": str(self.notebook_p1.id),
                "title": "Custom Lecture Title",
                "source_type": "image",
                "filename": "scan.png",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["document"]
        self.assertEqual(data["title"], "Custom Lecture Title")
        self.assertEqual(data["notebook"], str(self.notebook_p1.id))
        self.assertEqual(data["subject"], str(self.subject_p1.id))

        doc = Document.objects.get(pk=data["id"])
        self.assertEqual(doc.title, "Custom Lecture Title")
        self.assertEqual(doc.notebook_id, self.notebook_p1.id)

    def test_create_document_defaults_title_if_not_provided(self):
        resp = self.alice.post(
            "/api/v1/documents",
            {
                "profile": str(self.alice_profile_1.id),
                "source_type": "image",
                "filename": "physics_notes.jpg",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["document"]
        self.assertTrue(data["title"])
        self.assertIsNone(data["notebook"])

    def test_create_document_rejects_cross_profile_notebook(self):
        resp = self.alice.post(
            "/api/v1/documents",
            {
                "profile": str(self.alice_profile_1.id),
                "notebook": str(self.notebook_p2.id),  # Belongs to profile 2!
                "source_type": "image",
                "filename": "scan.png",
            },
            format="json",
        )
        self.assertIn(resp.status_code, [400, 422])

    # --- 2. Document PATCH Tests ---

    def test_patch_document_title(self):
        doc, _ = self._create_doc(title="Old Title")
        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {"title": "New Updated Title"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "New Updated Title")
        doc.refresh_from_db()
        self.assertEqual(doc.title, "New Updated Title")

    def test_patch_document_empty_title_defaults(self):
        doc, _ = self._create_doc(title="Old Title")
        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {"title": "   "},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Untitled Note")

    def test_patch_document_subject_and_notebook(self):
        doc, _ = self._create_doc(subject=None, notebook=None)
        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {
                "subject": str(self.subject_p1.id),
                "notebook": str(self.notebook_p1.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.subject_id, self.subject_p1.id)
        self.assertEqual(doc.notebook_id, self.notebook_p1.id)

    def test_patch_document_rejects_cross_profile_subject(self):
        doc, _ = self._create_doc(profile=self.alice_profile_1)
        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {"subject": str(self.subject_p2.id)},  # belongs to profile 2
            format="json",
        )
        self.assertIn(resp.status_code, [400, 422])

    def test_patch_document_rejects_cross_profile_notebook(self):
        doc, _ = self._create_doc(profile=self.alice_profile_1)
        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {"notebook": str(self.notebook_p2.id)},  # belongs to profile 2
            format="json",
        )
        self.assertIn(resp.status_code, [400, 422])

    def test_patch_document_rejects_conflicting_notebook_subject(self):
        doc, _ = self._create_doc(profile=self.alice_profile_1, subject=self.subject_p1)
        other_subject = Subject.objects.create(profile=self.alice_profile_1, name="Chemistry")
        other_notebook = Notebook.objects.create(profile=self.alice_profile_1, subject=other_subject, title="Chem")

        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {"notebook": str(other_notebook.id)},
            format="json",
        )
        self.assertIn(resp.status_code, [400, 422])

    def test_patch_document_immutable_fields_ignored(self):
        doc, _ = self._create_doc(profile=self.alice_profile_1)
        orig_source = doc.source
        orig_created_at = doc.created_at

        resp = self.alice.patch(
            f"/api/v1/documents/{doc.id}",
            {
                "profile": str(self.alice_profile_2.id),
                "source": "canvas",
                "created_at": "2020-01-01T00:00:00Z",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.profile_id, self.alice_profile_1.id)
        self.assertEqual(doc.source, orig_source)
        self.assertEqual(doc.created_at, orig_created_at)

    # --- 3. Document DELETE Tests ---

    def test_delete_document_success(self):
        doc, _ = self._create_doc()
        resp = self.alice.delete(f"/api/v1/documents/{doc.id}")
        self.assertEqual(resp.status_code, 204)

        # Subsequent GET yields 404
        get_resp = self.alice.get(f"/api/v1/documents/{doc.id}")
        self.assertEqual(get_resp.status_code, 404)
        self.assertFalse(Document.objects.filter(pk=doc.id).exists())

    def test_delete_document_cascades_all_related_models(self):
        doc, page = self._create_doc()
        revision = DocumentPageRevision.objects.create(
            page=page,
            revision_number=1,
            content_hash="hash1",
            content_snapshot={"lines": []},
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
        )
        line = DocumentLine.objects.create(
            page_revision=revision,
            line_index=0,
            text="Hello world test line",
        )
        chunk = NoteChunk.objects.create(
            document=doc,
            profile=self.alice_profile_1,
            subject=self.subject_p1,
            revision_id=revision.id,
            content="Hello world test line",
            content_hash="chunkhash1",
            source_type=doc.source_type,
            page_start=1,
            page_end=1,
        )
        enriched = EnrichedNote.objects.create(
            document=doc,
            content_hash="enrichhash1",
            provider="test",
            model="test",
        )
        block = EnrichedNoteBlock.objects.create(
            enriched_note=enriched,
            block_index=0,
            block_type="concept_expansion",
            title="Concept",
            content="Expansion",
            generation_method="synthesized",
            source_chunk_ids=[str(chunk.id)],
        )
        citation = CitationBlock.objects.create(
            enriched_note_block=block,
            source_refs=[],
            verification_status="supported",
            verification_score=1.0,
            verifier_version="v1",
        )
        question = Question.objects.create(
            document=doc,
            source_revision_id=revision.id,
            source_chunk_id=chunk.id,
            prompt="What is this note about?",
            content_hash="qhash1",
            question_key="qkey1",
            generation_model="test",
            prompt_version="v1",
        )

        resp = self.alice.delete(f"/api/v1/documents/{doc.id}")
        self.assertEqual(resp.status_code, 204)

        # Assert cascades across all 8 related models
        self.assertFalse(DocumentPage.objects.filter(pk=page.id).exists())
        self.assertFalse(DocumentPageRevision.objects.filter(pk=revision.id).exists())
        self.assertFalse(DocumentLine.objects.filter(pk=line.id).exists())
        self.assertFalse(NoteChunk.objects.filter(pk=chunk.id).exists())
        self.assertFalse(EnrichedNote.objects.filter(pk=enriched.id).exists())
        self.assertFalse(EnrichedNoteBlock.objects.filter(pk=block.id).exists())
        self.assertFalse(CitationBlock.objects.filter(pk=citation.id).exists())
        self.assertFalse(Question.objects.filter(pk=question.id).exists())

    def test_delete_document_cleans_up_minio_storage(self):
        doc, page = self._create_doc()
        storage = get_object_storage()
        storage.store_bytes(page.image_ref, b"fake_png_data")
        self.assertTrue(storage.exists(page.image_ref))

        # Also add a digitized document PDF
        pdf_ref = f"{doc.profile_id}/{doc.pk}/sample.pdf"
        storage.store_bytes(pdf_ref, b"fake_pdf_data")
        DigitizedDocument.objects.create(
            document=doc,
            content_hash="pdfhash",
            pdf_ref=pdf_ref,
            renderer_version="v1",
        )
        self.assertTrue(storage.exists(pdf_ref))

        resp = self.alice.delete(f"/api/v1/documents/{doc.id}")
        self.assertEqual(resp.status_code, 204)

        # MinIO storage objects must be cleaned up
        self.assertFalse(storage.exists(page.image_ref))
        self.assertFalse(storage.exists(pdf_ref))

    def test_delete_document_cancels_active_jobs(self):
        doc, page = self._create_doc()
        job = Job.objects.create(
            job_type="enrich",
            resource_type="document",
            resource_id=str(doc.pk),
            profile_id=doc.profile_id,
            idempotency_key=f"test_enrich_{doc.pk}",
            status=Job.Status.QUEUED,
        )

        resp = self.alice.delete(f"/api/v1/documents/{doc.id}")
        self.assertEqual(resp.status_code, 204)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CANCELLED)

    def test_worker_safety_on_deleted_document(self):
        doc, page = self._create_doc()
        job = Job.objects.create(
            job_type="index",
            resource_type="document",
            resource_id=str(doc.pk),
            profile_id=doc.profile_id,
            idempotency_key=f"test_index_{doc.pk}",
            status=Job.Status.QUEUED,
        )

        # Delete document before job runs
        doc.delete()

        # Running job must not raise or crash
        run_index_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CANCELLED)

    def test_delete_document_authorization(self):
        doc, _ = self._create_doc(profile=self.alice_profile_1)

        # Bob cannot delete Alice's document
        resp = self.bob.delete(f"/api/v1/documents/{doc.id}")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Document.objects.filter(pk=doc.id).exists())

    def test_delete_document_profile_isolation(self):
        doc, _ = self._create_doc(profile=self.alice_profile_1)

        # Alice cannot delete document using profile 2 context
        resp = self.alice.delete(
            f"/api/v1/documents/{doc.id}",
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_2.id),
        )
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Document.objects.filter(pk=doc.id).exists())

        # Alice CAN delete document using profile 1 context
        resp_ok = self.alice.delete(
            f"/api/v1/documents/{doc.id}",
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_1.id),
        )
        self.assertEqual(resp_ok.status_code, 204)
        self.assertFalse(Document.objects.filter(pk=doc.id).exists())

    # --- 4. Subject DELETE & PATCH Tests ---

    def test_delete_subject_preserves_notes_as_unfiled(self):
        subject = Subject.objects.create(profile=self.alice_profile_1, name="Discrete Math")
        notebook = Notebook.objects.create(profile=self.alice_profile_1, subject=subject, title="DM Notebook")
        doc, _ = self._create_doc(profile=self.alice_profile_1, subject=subject, notebook=notebook)

        resp = self.alice.delete(f"/api/v1/subjects/{subject.id}")
        self.assertEqual(resp.status_code, 204)

        # Subject is deleted
        self.assertFalse(Subject.objects.filter(pk=subject.id).exists())

        # Document and notebook still exist, but subject is SET_NULL
        doc.refresh_from_db()
        notebook.refresh_from_db()
        self.assertIsNone(doc.subject)
        self.assertIsNone(notebook.subject)
        self.assertEqual(doc.notebook_id, notebook.id)

    def test_patch_subject_rename(self):
        subject = Subject.objects.create(profile=self.alice_profile_1, name="Intro AI")
        resp = self.alice.patch(
            f"/api/v1/subjects/{subject.id}",
            {"name": "Advanced Artificial Intelligence"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        subject.refresh_from_db()
        self.assertEqual(subject.name, "Advanced Artificial Intelligence")

    def test_patch_subject_profile_isolation(self):
        subject = Subject.objects.create(profile=self.alice_profile_1, name="Compilers")

        # Renaming subject with wrong profile header returns 404
        resp = self.alice.patch(
            f"/api/v1/subjects/{subject.id}",
            {"name": "Advanced Compilers"},
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_2.id),
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        subject.refresh_from_db()
        self.assertEqual(subject.name, "Compilers")

    def test_delete_subject_profile_isolation(self):
        subject = Subject.objects.create(profile=self.alice_profile_1, name="Networking")

        # Deleting with wrong profile header returns 404
        resp = self.alice.delete(
            f"/api/v1/subjects/{subject.id}",
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_2.id),
        )
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Subject.objects.filter(pk=subject.id).exists())

    # --- 5. Chat Profile Scoping Tests ---

    def test_chat_creation_scoped_to_active_profile(self):
        # Create chat in profile 1
        resp1 = self.alice.post(
            "/api/v1/chat/sessions",
            {"title": "Chat in P1"},
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_1.id),
            format="json",
        )
        self.assertEqual(resp1.status_code, 201)
        session1 = ChatSession.objects.get(pk=resp1.json()["id"])
        self.assertEqual(session1.profile_id, self.alice_profile_1.id)

        # Create chat in profile 2
        resp2 = self.alice.post(
            "/api/v1/chat/sessions",
            {"title": "Chat in P2"},
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_2.id),
            format="json",
        )
        self.assertEqual(resp2.status_code, 201)
        session2 = ChatSession.objects.get(pk=resp2.json()["id"])
        self.assertEqual(session2.profile_id, self.alice_profile_2.id)

    def test_chat_listing_isolated_by_active_profile(self):
        ChatSession.objects.create(profile=self.alice_profile_1, title="Alice P1 Chat")
        ChatSession.objects.create(profile=self.alice_profile_2, title="Alice P2 Chat")

        # Query with P1 active
        resp1 = self.alice.get(
            "/api/v1/chat/sessions",
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_1.id),
        )
        titles1 = [s["title"] for s in resp1.json().get("results", resp1.json())]
        self.assertIn("Alice P1 Chat", titles1)
        self.assertNotIn("Alice P2 Chat", titles1)

        # Query with P2 active
        resp2 = self.alice.get(
            "/api/v1/chat/sessions",
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_2.id),
        )
        titles2 = [s["title"] for s in resp2.json().get("results", resp2.json())]
        self.assertIn("Alice P2 Chat", titles2)
        self.assertNotIn("Alice P1 Chat", titles2)

    def test_chat_creation_rejects_subject_from_different_profile(self):
        resp = self.alice.post(
            "/api/v1/chat/sessions",
            {"title": "Cross Subject Chat", "subject": str(self.subject_p2.id)},
            HTTP_X_ACTIVE_PROFILE=str(self.alice_profile_1.id),
            format="json",
        )
        self.assertIn(resp.status_code, [400, 422])
