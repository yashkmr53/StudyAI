"""Canvas finalize → ingestion integration (§67) and rasterizer unit test."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.canvas.models import CanvasStroke
from apps.documents.models import Document, DocumentLine, DocumentPageRevision
from apps.jobs.models import Job
from apps.profiles.models import Profile
from tests.api.utils import authenticated_client


class RasterizerTests(TestCase):
    def test_produces_valid_png(self):
        from apps.canvas.raster import render_strokes_png

        png = render_strokes_png([[10.0, 10.0, 200.0, 120.0], [30.0, 30.0, 300.0, 90.0]])
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        # IHDR width/height at fixed offset (8 sig + 4 len + 4 tag)
        import struct

        w, h = struct.unpack(">II", png[16:24])
        self.assertEqual((w, h), (900, 620))
        self.assertTrue(png.endswith(b"IEND\xaeB`\x82"))


class CanvasFinalizeIngestionTests(TestCase):
    """§67: finalize = lock validation + finalization + document revision + OCR job."""

    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        response = self.alice.post(
            "/api/v1/canvas/sessions",
            {"profile": str(self.profile.id), "device_id": "devA"},
            content_type="application/json",
        )
        self.session = response.json()
        page_response = self.alice.post(
            "/api/v1/canvas/pages",
            {
                "session": self.session["id"],
                "page_number": 1,
                "device_id": "devA",
                "lock_generation": 1,
            },
            content_type="application/json",
        )
        self.page_id = page_response.json()["id"]
        CanvasStroke.objects.create(
            id="11111111-1111-1111-1111-111111111111",
            page_id=self.page_id,
            sequence_order=0,
            points=[10.0, 10.0, 400.0, 300.0],
            client_idempotency_key="stroke-1",
        )

    def finalize(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.alice.post(
                f"/api/v1/canvas/pages/{self.page_id}/finalize",
                {"device_id": "devA", "lock_generation": 1},
                content_type="application/json",
            )

    def test_finalize_creates_full_ingestion_chain(self):
        response = self.finalize()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["document_id"])
        self.assertTrue(body["revision_id"])
        self.assertTrue(body["job_id"])

        document = Document.objects.get(pk=body["document_id"])
        self.assertEqual(document.source, "canvas")
        self.assertEqual(document.source_type, "canvas_page")
        self.assertEqual(document.profile_id, self.profile.id)

        revision = DocumentPageRevision.objects.get(pk=body["revision_id"])
        self.assertEqual(revision.revision_number, 1)
        self.assertTrue(revision.page.image_ref)

        job = Job.objects.get(pk=body["job_id"])
        self.assertEqual(job.status, Job.Status.SUCCEEDED)  # eager execution
        self.assertGreater(DocumentLine.objects.filter(page_revision=revision).count(), 0)

    def test_second_page_reuses_document(self):
        first = self.finalize()
        page2 = self.alice.post(
            "/api/v1/canvas/pages",
            {
                "session": self.session["id"],
                "page_number": 2,
                "device_id": "devA",
                "lock_generation": 1,
            },
            content_type="application/json",
        ).json()
        with self.captureOnCommitCallbacks(execute=True):
            second = self.alice.post(
                f"/api/v1/canvas/pages/{page2['id']}/finalize",
                {"device_id": "devA", "lock_generation": 1},
                content_type="application/json",
            )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["document_id"], second.json()["document_id"])
        doc_pages = Document.objects.get(pk=first.json()["document_id"]).pages.count()
        self.assertEqual(doc_pages, 2)

    def test_already_finalized_returns_without_new_artifacts(self):
        self.finalize()
        documents_before = Document.objects.count()
        response = self.finalize()
        self.assertTrue(response.json()["already_finalized"])
        self.assertIsNone(response.json()["document_id"])
        self.assertEqual(Document.objects.count(), documents_before)
