"""Phase 6 tests (architecture §11–13, §26, §51): enrichment pipeline,
citations + verification, provenance independence, prompt registry,
evaluation harness."""
import hashlib
import json

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.ai_classroom.models import (
    CitationBlock,
    EnrichedNote,
    EnrichedNoteBlock,
    PromptVersion,
)
from apps.accounts.models import User
from apps.documents.models import Document
from apps.jobs.models import Job
from apps.profiles.models import Profile
from providers.registry import get_embedding_provider
from tests.api.test_retrieval import _make_ocr_document
from tests.api.utils import authenticated_client


class EnrichmentFlowTests(TestCase):
    """Full A–F pipeline over an indexed document."""

    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc_id = _make_ocr_document(
            self.alice,
            self.profile,
            [[
                "Dijkstra computes shortest paths in weighted graphs.",
                "It greedily selects the closest unvisited vertex.",
            ]],
        )
        from apps.retrieval.services import index_document

        index_document(Document.objects.get(pk=self.doc_id))

    def enrich(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.alice.post(f"/api/v1/documents/{self.doc_id}/enrich")

    def test_enrich_end_to_end_creates_verified_note(self):
        response = self.enrich()
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["job"]["id"]

        note = EnrichedNote.objects.filter(document_id=self.doc_id).order_by("-created_at").first()
        self.assertIsNotNone(note)
        self.assertEqual(note.generation_job.status, Job.Status.SUCCEEDED)

        detail = self.alice.get(f"/api/v1/documents/{self.doc_id}/enrichment").json()
        self.assertEqual(detail["id"], str(note.id))
        self.assertGreaterEqual(len(detail["blocks"]), 2)  # overview + key concepts

        methods = {b["generation_method"] for b in detail["blocks"]}
        self.assertEqual(methods, {"llm"})
        for block in detail["blocks"]:
            citation = block["citation"]
            self.assertIsNotNone(citation)
            self.assertIn(citation["verification_status"],
                          {"supported", "partially_supported", "unsupported"})
            self.assertEqual(citation["verifier_version"], "sim-v1")

        first = detail["blocks"][1]
        self.assertEqual(first["citation"]["verification_status"], "supported")
        self.assertEqual(
            first["citation"]["source_refs"][0]["chunk_id"],
            first["source_chunk_ids"][0],
        )

    def test_second_enrich_returns_existing_note(self):
        first = self.enrich()
        second = self.enrich()
        second_body = second.json()
        if second_body["enriched_note"]:
            self.assertEqual(second_body["enriched_note"]["id"],
                             str(EnrichedNote.objects.filter(document_id=self.doc_id).order_by("-created_at").first().pk))
        self.assertEqual(
            EnrichedNote.objects.filter(document_id=self.doc_id, superseded=False).count(), 1
        )
        _ = first

    def test_edit_marks_enrichment_ai_stale(self):
        self.enrich()
        from apps.documents.models import DocumentPage

        page = DocumentPage.objects.get(document_id=self.doc_id, page_number=1)
        self.alice.post(
            f"/api/v1/documents/{self.doc_id}/revisions",
            {"page_id": str(page.pk), "lines": [{"line_index": 0, "text": "Brand new content"}]},
            content_type="application/json",
        )
        # user-edit revisions enqueue index jobs; run pending index work eagerly
        from apps.retrieval.services import index_document

        index_document(Document.objects.get(pk=self.doc_id))
        note = EnrichedNote.objects.filter(document_id=self.doc_id).order_by("-created_at").first()
        self.assertTrue(note.ai_stale)

    def test_foreign_user_isolated(self):
        self.enrich()
        self.assertEqual(
            self.bob.get(f"/api/v1/documents/{self.doc_id}/enrichment").status_code, 404
        )
        self.assertEqual(self.bob.post(f"/api/v1/documents/{self.doc_id}/enrich").status_code, 404)


class RefreshAiTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc_id = _make_ocr_document(
            self.alice, self.profile, [["Alpha beta gamma delta epsilon zeta."]]
        )

    def test_refresh_creates_new_generation_retaining_old(self):
        with self.captureOnCommitCallbacks(execute=True):
            first = self.alice.post(f"/api/v1/documents/{self.doc_id}/enrich")
        self.assertEqual(first.status_code, 202)
        old = EnrichedNote.objects.get(document_id=self.doc_id, superseded=False)

        with self.captureOnCommitCallbacks(execute=True):
            refresh = self.alice.post(f"/api/v1/documents/{self.doc_id}/refresh-ai")
        self.assertEqual(refresh.status_code, 202)

        notes = EnrichedNote.objects.filter(document_id=self.doc_id).order_by("-created_at")
        self.assertEqual(notes.count(), 2)
        self.assertFalse(notes.first().superseded)
        old.refresh_from_db()
        self.assertTrue(old.superseded)


class VerifierTests(TestCase):
    def test_classification_thresholds(self):
        from apps.ai_classroom.services import EvidenceVerifier

        self.assertEqual(EvidenceVerifier.verify(block := "x", [])[0], "not_verified")

        block = "Dijkstra computes shortest paths in weighted graphs"
        exact = ["Dijkstra computes shortest paths in weighted graphs"]
        partial = ["weighted graphs and their properties"]
        unrelated = ["Photosynthesis converts light into chemical energy"]

        status, score = EvidenceVerifier._classify(block, exact)
        self.assertEqual(status, "supported")
        self.assertGreaterEqual(score, 0.60)

        status_partial, score_partial = EvidenceVerifier._classify(block, partial)
        self.assertIn(status_partial, {"partially_supported", "unsupported"})

        status_unrelated, score_unrelated = EvidenceVerifier._classify(block, unrelated)
        self.assertEqual(status_unrelated, "unsupported")


class PromptRegistryTests(TestCase):
    def test_prompts_seeded_and_active(self):
        from apps.ai_classroom.prompts import seed_prompt_versions

        created = seed_prompt_versions()
        again = seed_prompt_versions()
        self.assertEqual(created, 3)
        self.assertEqual(again, 0)
        for name in ("enrichment_draft", "gap_detection", "gap_filling"):
            prompt = PromptVersion.objects.get(prompt_name=name, version="v1")
            self.assertTrue(prompt.is_active)
            self.assertIn(prompt.qualified_name,
                          {"enrichment_draft:v1", "gap_detection:v1", "gap_filling:v1"})


class EvalHarnessTests(TestCase):
    def _user(self):
        return User.objects.get_or_create(email="eval@example.com")[0]

    def test_citation_metrics_math(self):
        from apps.evaluation.runner import record_run, run_citation_cases

        cases = [
            {"block_content": "Dijkstra finds shortest paths",
             "cited_chunk_contents": ["Dijkstra shortest paths algorithm details"],
             "expected_status": "supported"},
            {"block_content": "Totally different topic about photosynthesis",
             "cited_chunk_contents": ["Dijkstra shortest paths algorithm details"],
             "expected_status": "unsupported"},
        ]
        metrics = run_citation_cases(cases)
        run = record_run("citation", "fixture", len(cases), metrics)
        self.assertEqual(metrics["support_precision"], 1.0)
        self.assertEqual(metrics["support_recall"], 1.0)
        self.assertEqual(run.metrics["cases"], 2)

    def test_retrieval_metrics_math(self):
        from django.test import Client

        user = self._user()
        from apps.retrieval.retrieval import RetrievalService

        # build a tiny indexed corpus directly
        from apps.profiles.models import Profile
        profile = Profile.objects.create(user=user, name="EvalProfile")
        doc = Document.objects.create(profile=profile, source="upload", source_type="image")
        evidence = get_embedding_provider().embed(["alpha beta gamma"], model_version="hashing-384-v1")[0]
        from apps.retrieval.models import NoteChunk

        chunk = NoteChunk.objects.create(
            document=doc, profile=profile,
            revision_id="00000000-0000-0000-0000-000000000001",
            revision_ids=[], page_start=1, page_end=1, chunk_index=0,
            content="alpha beta gamma", content_hash="h" * 64, source_type="image",
            embedding=evidence, embedding_model="hashing", embedding_version="hashing-384-v1",
        )
        metrics = RetrievalSearchRunner(user, [str(chunk.pk)])
        self.assertEqual(metrics["recall_at_k"], 1.0)


def RetrievalSearchRunner(user, expected_ids):
    from apps.evaluation.runner import run_retrieval_cases

    query_words = "alpha beta gamma"
    return run_retrieval_cases([{"query": query_words, "expected_chunk_ids": expected_ids}], user, k=5)
