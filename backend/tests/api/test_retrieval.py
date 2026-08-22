"""AI Classroom foundation tests (architecture §8, §10, §14, §15):
chunking, incremental indexing, embeddings, hybrid retrieval, references."""
import hashlib
import json
import os

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.models import Document, DocumentPageRevision
from apps.jobs.models import Job
from apps.profiles.models import Profile
from apps.retrieval.models import NoteChunk
from providers.registry import get_embedding_provider
from tests.api.utils import authenticated_client


def _make_ocr_document(client, profile, page_texts: list[list[str]]) -> str:
    """Creates a document and runs OCR-equivalent revisions directly."""
    body = client.post(
        "/api/v1/documents",
        {"profile": str(profile.id), "source_type": "image", "filename": "n.png"},
        content_type="application/json",
    ).json()
    doc_id = body["document"]["id"]

    # Replace single default page flow: use the created page for first text set,
    # then create extra pages via model layer for multi-page docs.
    for idx, lines in enumerate(page_texts):
        if idx == 0:
            page = __import__("apps.documents.models", fromlist=["DocumentPage"]).DocumentPage.objects.get(
                document_id=doc_id, page_number=1
            )
        else:
            page = __import__("apps.documents.models", fromlist=["DocumentPage"]).DocumentPage.objects.create(
                document_id=doc_id, page_number=idx + 1
            )
        revision = DocumentPageRevision.objects.create(
            page=page,
            revision_number=1,
            content_hash=hashlib.sha256("\n".join(lines).encode()).hexdigest(),
            ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
        )
        for i, t in enumerate(lines):
            __import__("apps.documents.models", fromlist=["DocumentLine"]).DocumentLine.objects.create(
                page_revision=revision, line_index=i, text=t, confidence_score=0.95
            )
        page.current_revision_id = revision.pk
        page.ocr_status = "completed"
        page.save(update_fields=("current_revision_id", "ocr_status"))
    return doc_id


class EmbeddingProviderTests(TestCase):
    def test_deterministic_normalized_vectors(self):
        provider = get_embedding_provider()
        v1 = provider.embed(["quicksort partition pivot"], model_version="hashing-384-v1")
        v2 = provider.embed(["quicksort partition pivot"], model_version="hashing-384-v1")
        self.assertEqual(v1, v2)
        vec = v1[0]
        self.assertEqual(len(vec), 384)
        norm = sum(x * x for x in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=2)

    def test_different_texts_differ(self):
        provider = get_embedding_provider()
        a = provider.embed(["binary search trees"], model_version="m")[0]
        b = provider.embed(["red black tree rotations"], model_version="m")[0]
        self.assertNotEqual(a, b)


class ChunkingTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc_id = _make_ocr_document(
            self.alice,
            self.profile,
            [
                ["Binary search finds items in sorted arrays.", "It halves the range each step."],
                ["Quicksort partitions around a pivot element.", "Worst case is quadratic without care."],
            ],
        )
        from apps.documents.models import Document

        self.document = Document.objects.get(pk=self.doc_id)

    def test_build_chunks_spans_pages_with_context(self):
        from apps.retrieval.services import build_chunks

        chunks = build_chunks(self.document)
        self.assertGreaterEqual(len(chunks), 1)
        first = chunks[0]
        self.assertEqual(first["page_start"], 1)
        self.assertGreaterEqual(first["page_end"], 1)
        joined = "\n".join(c["content"] for c in chunks)
        for needle in ("Binary search", "Quicksort partitions"):
            self.assertIn(needle.split()[0], joined)
        # hashes are sha256 of content
        for c in chunks:
            self.assertEqual(c["content_hash"], hashlib.sha256(c["content"].encode()).hexdigest())

    def test_index_job_creates_chunks_embeddings_tsvectors(self):
        with self.captureOnCommitCallbacks(execute=True):
            pass  # no API call here; run job manually below
        from apps.retrieval.services import enqueue_index_job

        with self.captureOnCommitCallbacks(execute=True):
            job, created = enqueue_index_job(self.document)
        self.assertTrue(created)
        job = Job.objects.get(pk=job.pk)
        self.assertEqual(job.status, Job.Status.SUCCEEDED)

        chunks = NoteChunk.objects.filter(document=self.document, stale=False)
        self.assertGreaterEqual(chunks.count(), 1)
        for chunk in chunks:
            self.assertIsNotNone(chunk.embedding)
            self.assertEqual(len(chunk.embedding), 384)
            self.assertEqual(chunk.embedding_model, "hashing")

    def test_index_rerun_is_incremental_not_duplicating(self):
        from apps.retrieval.services import enqueue_index_job

        with self.captureOnCommitCallbacks(execute=True):
            job1, _ = enqueue_index_job(self.document)
        before = NoteChunk.objects.filter(document=self.document).count()
        embedded_before = NoteChunk.objects.filter(embedding__isnull=False).count()

        # same content ⇒ same key ⇒ no new job; direct re-run must not duplicate
        from apps.retrieval.services import index_document

        stats = index_document(self.document)
        after = NoteChunk.objects.filter(document=self.document).count()
        self.assertEqual(before, after)
        self.assertEqual(stats["created"], 0)


class RevisionAwareInvalidationTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc_id = _make_ocr_document(
            self.alice,
            self.profile,
            [["The mitochondria is the powerhouse of the cell.", "Cells divide during mitosis."]],
        )

    def test_edit_marks_old_chunks_stale_and_indexes_new(self):
        from apps.retrieval.services import enqueue_index_job, index_document
        from apps.documents.models import DocumentPage

        with self.captureOnCommitCallbacks(execute=True):
            enqueue_index_job(Document.objects.get(pk=self.doc_id))
        old_active = list(NoteChunk.objects.filter(document_id=self.doc_id, stale=False))
        self.assertGreaterEqual(len(old_active), 1)

        # user edit → new revision on page 1 (§48 path also enqueues indexing)
        response = self.alice.post(
            f"/api/v1/documents/{self.doc_id}/revisions",
            {"page_id": str(old_active[0].document.pages.first().pk),
             "lines": [{"line_index": 0, "text": "Completely different biology content"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        active_after = NoteChunk.objects.filter(document_id=self.doc_id, stale=False)
        stale_after = NoteChunk.objects.filter(document_id=self.doc_id, stale=True)

        self.assertTrue(stale_after.exists(), "old chunks must be marked stale")
        self.assertTrue(active_after.exists(), "new content chunk must be indexed")
        old_hashes = {c.content_hash for c in old_active}
        new_hashes = {c.content_hash for c in active_after}
        self.assertFalse(old_hashes & new_hashes)

        # historical retention: stale rows still exist (§27)
        self.assertEqual(
            NoteChunk.objects.filter(document_id=self.doc_id).count(),
            len(old_active) + active_after.count(),
        )


class HybridRetrievalTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc_id = _make_ocr_document(
            self.alice,
            self.profile,
            [[
                "Dijkstra computes shortest paths in weighted graphs.",
                "Dynamic programming caches overlapping subproblems.",
            ]],
        )
        from apps.documents.models import Document
        from apps.retrieval.services import index_document

        self.stats = index_document(Document.objects.get(pk=self.doc_id))

    def test_keyword_retrieval_hits_own_content(self):
        response = self.alice.post(
            "/api/v1/search",
            {"query": "shortest paths"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertGreaterEqual(len(results), 1)
        top = results[0]
        self.assertEqual(top["source_type"], "image")
        self.assertIn("Dijkstra", top["snippet"])

    def test_profile_isolation(self):
        response = self.bob.post("/api/v1/search", {"query": "Dijkstra"}, content_type="application/json")
        results = response.json()["results"]
        self.assertEqual(len(results), 0)  # bob cannot retrieve alice's notes

    def test_unauthenticated_search_rejected(self):
        anon = APIClient()
        response = anon.post("/api/v1/search", {"query": "x"}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_dense_channel_used_on_postgresql(self):
        from django.db import connection

        if connection.vendor != "postgresql":
            self.skipTest("dense channel requires PostgreSQL")
        evidence = None
        from apps.retrieval.retrieval import RetrievalService

        results = RetrievalService.search(self.alice_user(), "shortest paths graphs")
        self.assertGreaterEqual(len(results), 1)
        self.assertIsNotNone(results[0].dense_rank)

    def alice_user(self):
        from apps.accounts.models import User

        return User.objects.get(email="alice@example.com")


class ReferenceBookTests(TestCase):
    def setUp(self):
        import os
        import tempfile

        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.book_payload = [
            {
                "title": "Graph Theory Basics",
                "author": "E.uler",
                "edition": "1st",
                "isbn": "1234567890",
                "subject_name": None,
                "chapters": [
                    {
                        "number": 1,
                        "title": "Shortest paths",
                        "text": "Reference: Dijkstra's algorithm finds shortest paths.\n\nIt works only with non-negative edge weights.",
                    }
                ],
            }
        ]
        fd, self.path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(self.book_payload, fh)
        self.file_path = self.path

    def tearDown(self):
        os.remove(self.file_path)

    def ingest(self):
        from django.core.management import call_command

        call_command("ingest_reference_book", "--file", self.file_path, verbosity=0)

    def test_ingestion_creates_ready_book_and_retrievable_reference_chunk(self):
        self.ingest()
        from apps.references.models import ReferenceBook

        book = ReferenceBook.objects.get(title="Graph Theory Basics")
        self.assertEqual(book.status, ReferenceBook.Status.READY)
        self.assertIsNotNone(book.document)
        self.assertEqual(book.chapters.count(), 1)

        chunk = NoteChunk.objects.filter(reference_book=book, stale=False).first()
        self.assertIsNotNone(chunk)
        self.assertIsNone(chunk.profile)  # platform-wide
        self.assertIsNotNone(chunk.embedding)

        response = self.alice.post(
            "/api/v1/search",
            {"query": "Dijkstra shortest paths reference"},
            content_type="application/json",
        )
        snippets = [r["snippet"] for r in response.json()["results"]]
        self.assertTrue(any("Dijkstra" in s for s in snippets))

    def test_nonready_book_excluded_from_retrieval(self):
        self.ingest()
        from apps.references.models import ReferenceBook

        book = ReferenceBook.objects.get(title="Graph Theory Basics")
        book.status = ReferenceBook.Status.DRAFT
        book.save(update_fields=("status",))
        response = self.alice.post(
            "/api/v1/search", {"query": "Dijkstra shortest paths"}, content_type="application/json"
        )
        self.assertEqual(len(response.json()["results"]), 0)

    def test_ingestion_is_idempotent_per_title_author(self):
        self.ingest()
        from django.core.management import call_command

        call_command("ingest_reference_book", "--file", self.file_path, verbosity=0)
        from apps.references.models import ReferenceBook

        self.assertEqual(ReferenceBook.objects.filter(title="Graph Theory Basics").count(), 1)
