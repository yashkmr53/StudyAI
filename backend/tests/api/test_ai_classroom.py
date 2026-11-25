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
        self.assertTrue(methods.issubset({"llm", "rule_based", "transcribed", "user_edited"}))
        self.assertGreater(len(methods), 0)
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

    def test_enqueue_enrichment_rejected_if_ocr_in_progress(self):
        from apps.documents.models import DocumentPage
        page = DocumentPage.objects.filter(document_id=self.doc_id).first()
        page.review_status = DocumentPage.ReviewStatus.OCR_PROCESSING
        page.save(update_fields=("review_status",))

        response = self.alice.post(f"/api/v1/documents/{self.doc_id}/enrich")
        self.assertEqual(response.status_code, 422)
        error_msg = response.json().get("error", {}).get("message", "")
        self.assertIn("transcription is still processing", error_msg)

    def test_enqueue_enrichment_rejected_if_transcript_unapproved(self):
        from apps.documents.models import DocumentPage
        page = DocumentPage.objects.filter(document_id=self.doc_id).first()
        page.review_status = DocumentPage.ReviewStatus.PENDING_REVIEW
        page.is_approved = False
        page.save(update_fields=("review_status", "is_approved"))

        response = self.alice.post(f"/api/v1/documents/{self.doc_id}/enrich")
        self.assertEqual(response.status_code, 422)
        error_msg = response.json().get("error", {}).get("message", "")
        self.assertIn("transcript must be approved", error_msg)


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
        provider = get_embedding_provider()
        evidence = provider.embed(["alphabeta gamma"], model_version=provider.model_version)[0]
        from apps.retrieval.models import NoteChunk

        chunk = NoteChunk.objects.create(
            document=doc, profile=profile,
            revision_id="00000000-0000-0000-0000-000000000001",
            revision_ids=[], page_start=1, page_end=1, chunk_index=0,
            content="alpha beta gamma", content_hash="h" * 64, source_type="image",
            embedding=evidence, embedding_model=provider.model_name, embedding_version=provider.model_version,
        )
        metrics = RetrievalSearchRunner(user, [str(chunk.pk)])
        self.assertEqual(metrics["recall_at_k"], 1.0)


def RetrievalSearchRunner(user, expected_ids):
    from apps.evaluation.runner import run_retrieval_cases

    query_words = "alpha beta gamma"
    return run_retrieval_cases([{"query": query_words, "expected_chunk_ids": expected_ids}], user, k=5)


class RelevanceGateIntegrationTests(TestCase):
    def test_compute_embedding_similarity_uses_provider_vectors_for_paraphrases(self):
        from unittest.mock import MagicMock, patch
        from apps.ai_classroom.relevance_gate import compute_embedding_similarity

        mock_provider = MagicMock()
        mock_provider.model_version = "mock-v1"
        mock_provider.embed.return_value = [
            [0.8, 0.6, 0.0],
            [0.8, 0.6, 0.0],
        ]
        with patch("apps.ai_classroom.relevance_gate.get_embedding_provider", return_value=mock_provider):
            sim = compute_embedding_similarity("runtime efficiency", "asymptotic execution speed")

        self.assertGreater(sim, 0.95)
        mock_provider.embed.assert_called_once()

    def test_gap_detection_node_suppresses_irrelevant_distractors(self):
        from unittest.mock import MagicMock, patch
        from apps.ai_classroom.enrichment_nodes import gap_detection_node
        from apps.ai_classroom.prompts import seed_prompt_versions

        seed_prompt_versions()
        mock_llm = MagicMock()
        mock_llm.generate_structured.return_value = MagicMock(
            data={
                "gaps": [
                    {
                        "topic": "binary search complexity",
                        "why_missing": "Note describes binary search on sorted array but omits complexity",
                        "missing_from_note": "No O(log n) analysis",
                        "evidence_in_reference": "Binary search runs in O(log n) on a sorted array.",
                        "source_chunk_id": "ref-1",
                        "source_chunk_ids": ["ref-1"],
                    },
                    {
                        "topic": "chloroplast thylakoid membranes",
                        "why_missing": "Botany concept unrelated to algorithms",
                        "missing_from_note": "No mention of photosynthesis",
                        "evidence_in_reference": "Chloroplasts contain thylakoid membranes for photosynthesis.",
                        "source_chunk_ids": ["ref-2"],
                    },
                ]
            },
            provider="mock",
            model="mock",
        )
        state = {
            "job_id": "j-r3",
            "evidence_payload": {
                "has_reference_material": True,
                "user_chunks": [{"content": "Binary search locates a target element inside a sorted array."}],
                "reference_chunks": [
                    {"chunk_id": "ref-1", "content": "Binary search runs in O(log n) on a sorted array."},
                    {"chunk_id": "ref-2", "content": "Chloroplasts contain thylakoid membranes for photosynthesis."},
                ],
            },
        }
        with patch("apps.ai_classroom.enrichment_nodes.get_llm_provider", return_value=mock_llm):
            out = gap_detection_node(state)

        topics = [g["topic"] for g in out["gaps_result"]["gaps"]]
        self.assertIn("binary search complexity", topics)
        self.assertNotIn("chloroplast thylakoid membranes", topics)

    def test_coverage_comparison_node_filters_irrelevant_candidates(self):
        from apps.ai_classroom.enrichment_nodes import coverage_comparison_node

        state = {
            "evidence_payload": {
                "user_chunks": [{"content": "Binary search finds a target element in a sorted array."}],
            },
            "gap_candidates": [
                {
                    "concept": "binary search time complexity",
                    "source_chunk_id": "ref-1",
                    "source_content": "Binary search runs in O(log n) in a sorted array.",
                    "evidence_span": "sorted array binary search",
                    "confidence": 0.9,
                    "metadata": {},
                },
                {
                    "concept": "chloroplast thylakoid photosynthesis",
                    "source_chunk_id": "ref-2",
                    "source_content": "Chloroplasts perform photosynthesis using thylakoid membranes.",
                    "evidence_span": "chloroplast thylakoid photosynthesis",
                    "confidence": 0.9,
                    "metadata": {},
                },
            ],
        }
        out = coverage_comparison_node(state)
        concepts = [c["concept"] for c in out["gap_candidates"]]
        self.assertIn("binary search time complexity", concepts)
        self.assertNotIn("chloroplast thylakoid photosynthesis", concepts)
        self.assertEqual(out["coverage_summary"].get("irrelevant_filtered"), 1)
