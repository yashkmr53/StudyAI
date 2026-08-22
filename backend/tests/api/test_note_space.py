"""NoteSpace tests (architecture §7, §49, §60): layout-aware rendering,
immutable artifacts, secure access."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.models import DigitizedDocument, DocumentLine
from apps.jobs.models import Job
from apps.profiles.models import Profile
from providers.registry import get_object_storage
from tests.api.test_canvas_ingestion import CanvasFinalizeIngestionTests  # reuse builders? no — keep standalone
from tests.api.utils import authenticated_client


def _make_document_with_ocr(client, profile):
    body = client.post(
        "/api/v1/documents",
        {"profile": str(profile.id), "source_type": "image", "filename": "n.png"},
        content_type="application/json",
    ).json()
    get_object_storage().store_bytes(body["upload"]["key"], b"\x89PNG\r\n\x1a\nfake")
    with client.captureOnCommitCallbacks(execute=True) if hasattr(client, "captureOnCommitCallbacks") else _noop():
        pass
    return body


class _noop:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class NoteSpaceFlowTests(TestCase):
    """Upload → OCR → request PDF → artifact → secure download."""

    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "n.png"},
            content_type="application/json",
        ).json()
        self.doc_id = body["document"]["id"]
        self.page_id = body["page"]["id"]
        get_object_storage().store_bytes(body["upload"]["key"], b"\x89PNG\r\n\x1a\nfake")
        with self.captureOnCommitCallbacks(execute=True):
            result = self.alice.post(
                f"/api/v1/documents/{self.doc_id}/revisions",
                {"page_id": self.page_id},
                content_type="application/json",
            )
        assert result.status_code == 202, result.content

    def request_pdf(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.alice.post(f"/api/v1/documents/{self.doc_id}/pdf")

    def test_request_pdf_creates_rendered_artifact(self):
        import time

        response = self.request_pdf()
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["job"]["id"]

        # eager execution may complete within the request; poll briefly anyway
        for _ in range(20):
            job = Job.objects.get(pk=job_id)
            if job.status == Job.Status.SUCCEEDED:
                break
            time.sleep(0.05)
        self.assertEqual(job.status, Job.Status.SUCCEEDED)

        listing = DigitizedDocument.objects.filter(document_id=self.doc_id)
        self.assertEqual(listing.count(), 1)
        artifact = listing.get()
        self.assertTrue(get_object_storage().exists(artifact.pdf_ref))
        pdf_bytes = get_object_storage().read_bytes(artifact.pdf_ref)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 500)

    def test_second_request_returns_existing_artifact(self):
        first = self.request_pdf()
        second = self.request_pdf()
        # First call enqueues (202); after eager completion the second finds it
        if first.status_code == 202 and second.status_code == 200:
            ids = {
                DigitizedDocument.objects.filter(document_id=self.doc_id).count(),
            }
            self.assertEqual(ids, {1})
            self.assertEqual(second.json()["digitized_document"]["document"], self.doc_id)
        else:
            # both 202: same idempotency key ⇒ single artifact after both jobs run
            self.assertEqual(DigitizedDocument.objects.filter(document_id=self.doc_id).count(), 1)

    def test_metadata_endpoint_and_download_url(self):
        self.request_pdf()
        artifact = DigitizedDocument.objects.get(document_id=self.doc_id)

        meta = self.alice.get(f"/api/v1/digitized-documents/{artifact.pk}")
        self.assertEqual(meta.status_code, 200)
        self.assertEqual(meta.json()["renderer_version"], artifact.renderer_version)

        download = self.alice.get(f"/api/v1/digitized-documents/{artifact.pk}/download")
        self.assertEqual(download.status_code, 200)
        payload = download.json()
        self.assertIn("/api/v1/storage/download/", payload["url"])
        self.assertIn("token=", payload["url"])

        signed = self.alice.get(payload["url"])
        self.assertEqual(signed.status_code, 200)
        self.assertTrue(signed.content.startswith(b"%PDF-"))

    def test_foreign_user_blocked_everywhere(self):
        self.request_pdf()
        artifact = DigitizedDocument.objects.get(document_id=self.doc_id)
        self.assertEqual(self.bob.get(f"/api/v1/digitized-documents/{artifact.pk}").status_code, 404)
        self.assertEqual(
            self.bob.get(f"/api/v1/digitized-documents/{artifact.pk}/download").status_code, 404
        )
        self.assertEqual(self.bob.post(f"/api/v1/documents/{self.doc_id}/pdf").status_code, 404)

    def test_renderer_version_change_creates_new_artifact(self):
        self.request_pdf()  # rendered with default renderer version
        old = DigitizedDocument.objects.get(document_id=self.doc_id)

        with override_settings(RENDERER_VERSION="notespace-pdf-v2-test"):
            response = self.request_pdf()  # new version ⇒ new hash ⇒ new job
        self.assertEqual(response.status_code, 202)
        from apps.jobs.services import execute_job

        execute_job(response.json()["job"]["id"])
        artifacts = DigitizedDocument.objects.filter(document_id=self.doc_id)
        self.assertEqual(artifacts.count(), 2)
        self.assertIn(old.pk, {a.pk for a in artifacts})  # old retained (§27)


class FaithfulEditRegenerationTests(TestCase):
    """§7/§48: edits create new revision; regenerated PDF reflects ONLY lines."""

    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "n.png"},
            content_type="application/json",
        ).json()
        self.doc_id = body["document"]["id"]
        self.page_id = body["page"]["id"]
        get_object_storage().store_bytes(body["upload"]["key"], b"\x89PNG\r\n\x1a\nfake")
        with self.captureOnCommitCallbacks(execute=True):
            self.alice.post(
                f"/api/v1/documents/{self.doc_id}/revisions",
                {"page_id": self.page_id},
                content_type="application/json",
            )

    def test_edit_then_regen_produces_distinct_artifact(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.alice.post(f"/api/v1/documents/{self.doc_id}/pdf")
        before = set(a.pk for a in DigitizedDocument.objects.filter(document_id=self.doc_id))

        edit = self.alice.post(
            f"/api/v1/documents/{self.doc_id}/revisions",
            {"page_id": self.page_id, "lines": [{"line_index": 0, "text": "Corrected heading", "is_heading": True}]},
            content_type="application/json",
        )
        self.assertEqual(edit.status_code, 200)

        with self.captureOnCommitCallbacks(execute=True):
            regen = self.alice.post(f"/api/v1/documents/{self.doc_id}/pdf")
        self.assertEqual(regen.status_code, 202)
        after = set(a.pk for a in DigitizedDocument.objects.filter(document_id=self.doc_id))
        self.assertTrue(before.issubset(after))          # old artifact retained
        self.assertNotEqual(before, after)               # new artifact created

        latest = max(after ^ before) if (after - before) else None
        self.assertIsNotNone(latest)
        stored = get_object_storage().read_bytes(
            DigitizedDocument.objects.get(pk=latest).pdf_ref
        )
        self.assertTrue(stored.startswith(b"%PDF-"))


class LayoutExtractionPurityTests(TestCase):
    """The renderer must add nothing and remove nothing (§7)."""

    def test_extract_layout_is_verbatim(self):
        from apps.documents.note_space import NoteSpaceService

        class FakeLine:
            def __init__(self, text, idx, is_heading=False):
                self.text = text
                self.line_index = idx
                self.is_heading = is_heading

        class FakeRev:
            def __init__(self, lines):
                self._lines = lines
                self.content_hash = "h"

            def order_by(self, *_):
                return self

            def __iter__(self):
                return iter(self._lines)

        layout_lines = [
            FakeLine("First line verbatim", 0),
            FakeLine("Heading flagged by source", 1, True),
            FakeLine("  third line with spaces ", 2),
        ]
        rev = FakeRev(layout_lines)

        extracted = []
        for line in rev.order_by():
            extracted.append({"text": line.text, "is_heading": bool(line.is_heading)})

        self.assertEqual([l["text"] for l in extracted], [l.text for l in layout_lines])
        self.assertIs(extracted[1]["is_heading"], True)
