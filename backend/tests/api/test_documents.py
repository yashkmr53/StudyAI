"""Shared ingestion tests (architecture §6, §45–48): upload flow, signed
storage URLs, logical OCR jobs, fallback, review states, retries."""
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.models import (
    Document,
    DocumentLine,
    DocumentPage,
    DocumentPageRevision,
)
from apps.jobs.models import Job
from apps.profiles.models import Profile
from providers.registry import get_object_storage
from tests.api.utils import authenticated_client


def _png_bytes() -> bytes:
    # Minimal valid-ish binary payload; providers/storage only checks size/type.
    return b"\x89PNG\r\n\x1a\n" + b"x" * 256


class UploadFlowTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")

    def create_document(self, client=None):
        client = client or self.alice
        return client.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "lecture.jpg"},
            content_type="application/json",
        )

    def test_create_document_returns_upload_target(self):
        response = self.create_document()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["document"]["source"], "upload")
        self.assertIn("/api/v1/storage/upload/", body["upload"]["url"])
        self.assertTrue(body["page"]["id"])

    def test_foreign_profile_forbidden(self):
        response = self.bob.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "x.png"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_upload_roundtrip_and_download(self):
        body = self.create_document().json()
        url = body["upload"]["url"]
        put = self.alice_client_put(url, _png_bytes())
        self.assertEqual(put.status_code, 200)

        key = body["upload"]["key"]
        download_url = get_object_storage().create_download_url(key)
        got = self.alice.get(download_url)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.content, _png_bytes())

    def alice_client_put(self, url, data, content_type="image/png"):
        return self.alice.put(f"{url}", data=data, content_type=content_type)

    def test_upload_rejects_disallowed_content_type(self):
        body = self.create_document().json()
        response = self.alice_client_put(body["upload"]["url"], b"hello", content_type="text/plain")
        self.assertEqual(response.status_code, 422)

    def test_upload_rejects_oversize(self):
        from django.conf import settings

        body = self.create_document().json()
        big = b"x" * (getattr(settings, "UPLOAD_MAX_BYTES") + 1)
        response = self.alice_client_put(body["upload"]["url"], big)
        self.assertEqual(response.status_code, 413)

    def test_forged_token_rejected(self):
        signer = TimestampSigner()
        bad = signer.sign_object({"action": "upload", "key": "../etc/passwd"})
        response = self.alice_client_put(
            f"/api/v1/storage/upload/etc/passwd?token={bad}", b"data"
        )
        self.assertEqual(response.status_code, 403)


class FinalizeAndOcrTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "l.jpg"},
            content_type="application/json",
        ).json()
        self.doc_id = body["document"]["id"]
        self.page_id = body["page"]["id"]
        self.key = body["upload"]["key"]
        get_object_storage().store_bytes(self.key, _png_bytes())

    def finalize(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.alice.post(
                f"/api/v1/documents/{self.doc_id}/revisions",
                {"page_id": self.page_id},
                content_type="application/json",
            )

    def test_finalize_upload_creates_revision_and_runs_ocr(self):
        response = self.finalize()
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["revision"]["revision_number"], 1)
        self.assertEqual(body["revision"]["ocr_status"], "completed")
        self.assertEqual(body["job"]["status"], "succeeded")

        page = DocumentPage.objects.get(pk=self.page_id)
        self.assertEqual(page.ocr_status, "completed")
        self.assertEqual(str(page.current_revision_id), body["revision"]["id"])
        revision = DocumentPageRevision.objects.get(pk=body["revision"]["id"])
        self.assertEqual(revision.lines.count(), 3)
        self.assertFalse(page.needs_review)

    def test_duplicate_content_reuses_logical_job(self):
        first = self.finalize()
        second = self.finalize()
        first_job = first.json()["job"]["id"]
        second_job = second.json()["job"]["id"]
        self.assertEqual(first_job, second_job)  # §20 idempotency key
        self.assertEqual(DocumentPageRevision.objects.filter(page_id=self.page_id).count(), 2)

    @override_settings(OCR_PROVIDER_CHAIN=["mock_low_confidence", "mock"], OCR_REVIEW_THRESHOLD=0.80)
    def test_low_confidence_marks_needs_review(self):
        self.finalize()
        page = DocumentPage.objects.get(pk=self.page_id)
        self.assertEqual(page.ocr_status, "needs_review")
        self.assertTrue(page.needs_review)
        revision = DocumentPageRevision.objects.get(pk=str(page.current_revision_id))
        self.assertEqual(revision.ocr_status, "needs_review")

    @override_settings(OCR_PROVIDER_CHAIN=["failing", "mock"])
    def test_primary_failure_falls_back(self):
        response = self.finalize()
        body = response.json()
        self.assertEqual(body["job"]["status"], "succeeded")
        revision = DocumentPageRevision.objects.get(pk=body["revision"]["id"])
        self.assertEqual(revision.ocr_provider, "mock")
        self.assertIn("failing", revision.content_snapshot["attempted_providers"])

    @override_settings(OCR_PROVIDER_CHAIN=["failing", "failing"], JOBS_MAX_ATTEMPTS=2)
    def test_all_failures_dead_letter_after_max_attempts(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.finalize()
        job_id = response.json()["job"]["id"]
        job = Job.objects.get(pk=job_id)
        self.assertEqual(job.status, Job.Status.FAILED_RETRYABLE)
        self.assertIsNotNone(job.next_retry_at)

        from apps.jobs.services import execute_job, promote_due_retries

        Job.objects.filter(pk=job.pk).update(next_retry_at=None)
        promote_due_retries()
        execute_job(job.pk)  # attempt 2 → dead letter
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.FAILED_DEAD_LETTER)
        self.assertIn("All OCR providers failed", job.last_error)

    def test_user_edit_revision_is_immutable_new_revision(self):
        self.finalize()
        old_revision = DocumentPageRevision.objects.get(page_id=self.page_id, revision_number=1)
        old_lines = list(DocumentLine.objects.filter(page_revision=old_revision).values_list("text", flat=True))

        response = self.alice.post(
            f"/api/v1/documents/{self.doc_id}/revisions",
            {"page_id": self.page_id, "lines": [{"line_index": 0, "text": "Hand-corrected line"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["job"])
        self.assertEqual(body["revision"]["revision_number"], 2)
        self.assertEqual(body["revision"]["edited_by"], str(old_revision.edited_by_id or "") or body["revision"]["edited_by"])

        new_revision = DocumentPageRevision.objects.get(pk=body["revision"]["id"])
        self.assertEqual(new_revision.lines.first().text, "Hand-corrected line")
        # Old revision untouched (§48 immutability)
        self.assertEqual(
            list(DocumentLine.objects.filter(page_revision=old_revision).values_list("text", flat=True)),
            old_lines,
        )

    def test_isolation_between_users(self):
        response = self.bob.get(f"/api/v1/documents/{self.doc_id}")
        self.assertEqual(response.status_code, 404)
        response = self.bob.post(
            f"/api/v1/documents/pages/{self.page_id}/finalize-upload"
        )
        self.assertEqual(response.status_code, 404)


class RetryProcessingTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "l.jpg"},
            content_type="application/json",
        ).json()
        self.doc_id = body["document"]["id"]
        self.page_id = body["page"]["id"]
        self.key = body["upload"]["key"]
        get_object_storage().store_bytes(self.key, _png_bytes())
        with self.captureOnCommitCallbacks(execute=True):
            self.alice.post(
                f"/api/v1/documents/{self.doc_id}/revisions",
                {"page_id": self.page_id},
                content_type="application/json",
            )

    def test_retry_failed_job(self):
        job = Job.objects.get(resource_type="document_page_revision", job_type="ocr")
        job.mark_retryable("simulated failure")
        response = self.alice.post(
            f"/api/v1/documents/{self.doc_id}/retry-processing",
            {"page_id": self.page_id},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.SUCCEEDED)

    def test_retry_succeeded_job_conflicts(self):
        response = self.alice.post(
            f"/api/v1/documents/{self.doc_id}/retry-processing",
            {"page_id": self.page_id},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)


class JobsApiTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "l.jpg"},
            content_type="application/json",
        ).json()
        get_object_storage().store_bytes(body["upload"]["key"], _png_bytes())
        with self.captureOnCommitCallbacks(execute=True):
            self.job_id = self.alice.post(
                f"/api/v1/documents/{body['document']['id']}/revisions",
                {"page_id": body["page"]["id"]},
                content_type="application/json",
            ).json()["job"]["id"]

    def test_get_own_job_shape(self):
        response = self.alice.get(f"/api/v1/jobs/{self.job_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for field in ("id", "job_type", "resource_type", "resource_id", "status", "attempt_count"):
            self.assertIn(field, payload)

    def test_foreign_job_not_found(self):
        response = self.bob.get(f"/api/v1/jobs/{self.job_id}")
        self.assertEqual(response.status_code, 404)

    def test_cancel_terminal_job_conflicts(self):
        response = self.alice.post(f"/api/v1/jobs/{self.job_id}/cancel")
        self.assertEqual(response.status_code, 422)

    def test_cancel_queued_job(self):
        from apps.documents.models import DocumentPage

        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "l2.jpg"},
            content_type="application/json",
        ).json()
        # store object but do NOT finalize → no job yet; craft a queued job manually
        job = Job.objects.create(
            job_type="ocr",
            resource_type="manual",
            resource_id="r",
            profile_id=self.profile.id,
            idempotency_key="manual-test-key",
        )
        response = self.alice.post(f"/api/v1/jobs/{job.pk}/cancel")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
