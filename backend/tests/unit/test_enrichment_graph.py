"""Phase 3 LangGraph enrichment graph tests."""
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ai.langgraph.state.enrichment_state import EnrichmentState
from ai.langgraph.graphs.enrichment_graph import build_enrichment_graph, _branch_after_gap_detection
from apps.ai_classroom.enrichment_nodes import (
    citation_stitch_node,
    draft_node,
    evidence_verification_node,
    format_output_node,
    gap_detection_node,
    gap_fill_node,
    retrieve_chunks_node,
)


class MockLLMProvider:
    model_name = "mock-gpt"
    name = "mock"

    def generate_structured(self, *, prompt=None, schema=None, request_id=None):
        prompt_name = getattr(prompt, 'name', '')
        if prompt_name == "enrichment_draft":
            return type("R", (), {
                "data": {
                    "blocks": [
                        {"block_type": "overview", "content": "Dijkstra computes shortest paths.",
                         "generation_method": "llm", "source_chunk_ids": ["chunk-1"]},
                    ]
                },
                "model": "mock-gpt",
                "prompt_name": "enrichment_draft",
                "prompt_version": "v1",
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            })()
        elif prompt_name == "gap_detection":
            return type("R", (), {
                "data": {
                    "gaps": [
                        {"topic": "complexity", "reference_chunk_id": "ref-1"},
                    ]
                },
                "model": "mock-gpt",
                "prompt_name": "gap_detection",
                "prompt_version": "v1",
                "input_tokens": 10,
                "output_tokens": 15,
                "total_tokens": 25,
            })()
        elif prompt_name == "gap_filling":
            return type("R", (), {
                "data": {
                    "blocks": [
                        {"block_type": "gap_fill", "content": "Time complexity is O(E log V).",
                         "generation_method": "llm", "source_chunk_ids": ["ref-1"]},
                    ]
                },
                "model": "mock-gpt",
                "prompt_name": "gap_filling",
                "prompt_version": "v1",
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            })()
        return type("R", (), {"data": {}, "model": "mock-gpt", "prompt_name": "", "prompt_version": "v1",
                               "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})()


class MockChunk:
    def __init__(self, pk, content, source_type="note", document_id="doc-1", page_start=1, page_end=1, revision_ids=None):
        self.pk = pk
        self.content = content
        self.source_type = source_type
        self.document_id = document_id
        self.page_start = page_start
        self.page_end = page_end
        self.revision_ids = revision_ids or []
        self.reference_book = None


class TestEnrichmentGraphNodes(TestCase):
    def test_retrieve_node_returns_chunks(self):
        with patch("apps.ai_classroom.enrichment_nodes.Document.objects.select_related") as mock_doc_qs, \
             patch("apps.ai_classroom.enrichment_nodes.NoteChunk.objects.filter") as mock_nc_filter:
            mock_doc = MagicMock()
            mock_doc.pk = "doc-1"
            mock_doc.profile_id = "profile-1"
            mock_doc_qs.return_value.get.return_value = mock_doc

            mock_user_qs = MagicMock()
            mock_user_qs.return_value.select_related.return_value.order_by.return_value.__getitem__.return_value = []
            mock_ref_qs = MagicMock()
            mock_ref_qs.return_value.select_related.return_value.order_by.return_value.__getitem__.return_value = []

            mock_nc_filter.side_effect = lambda *args, **kwargs: (
                mock_user_qs if args and args[0] == "document" else mock_ref_qs
            )

            state = EnrichmentState(
                document_id="doc-1", job_id="job-1",
                user_chunks=[], reference_chunks=[], evidence_payload={},
                draft_result={}, gaps_result={}, fill_result={},
                all_blocks=[], stitched_blocks=[], errors=[], execution_metadata={},
            )

            result = retrieve_chunks_node(state)
            self.assertIn("evidence_payload", result)

    def test_draft_node_returns_blocks(self):
        state = EnrichmentState(
            document_id="doc-1", job_id="job-1",
            user_chunks=[], reference_chunks=[], evidence_payload={"user_chunks": [], "reference_chunks": []},
            draft_result={}, gaps_result={}, fill_result={},
            all_blocks=[], stitched_blocks=[], errors=[], execution_metadata={},
        )

        with patch("apps.ai_classroom.enrichment_nodes.active_prompt") as mock_prompt, \
             patch("apps.ai_classroom.enrichment_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.ai_classroom.enrichment_nodes.validate_stage_output"), \
             patch("apps.ai_classroom.enrichment_nodes.log_llm_call"):
            mock_prompt.return_value = MagicMock(version="v1", template="Draft enrichment")
            mock_get_llm.return_value = MockLLMProvider()
            result = draft_node(state)

            self.assertIn("draft_result", result)
            self.assertIn("blocks", result["draft_result"])

    def test_gap_detection_node_returns_gaps(self):
        state = EnrichmentState(
            document_id="doc-1", job_id="job-1",
            user_chunks=[], reference_chunks=[], evidence_payload={"user_chunks": [], "reference_chunks": []},
            draft_result={}, gaps_result={}, fill_result={},
            all_blocks=[], stitched_blocks=[], errors=[], execution_metadata={},
        )

        with patch("apps.ai_classroom.enrichment_nodes.active_prompt") as mock_prompt, \
             patch("apps.ai_classroom.enrichment_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.ai_classroom.enrichment_nodes.validate_stage_output"), \
             patch("apps.ai_classroom.enrichment_nodes.log_llm_call"):
            mock_prompt.return_value = MagicMock(version="v1", template="Detect gaps")
            mock_get_llm.return_value = MockLLMProvider()
            result = gap_detection_node(state)

            self.assertIn("gaps_result", result)
            self.assertIn("gaps", result["gaps_result"])

    def test_gap_fill_node_skips_when_no_gaps(self):
        state = EnrichmentState(
            document_id="doc-1", job_id="job-1",
            user_chunks=[], reference_chunks=[], evidence_payload={"user_chunks": [], "reference_chunks": []},
            draft_result={}, gaps_result={"gaps": []}, fill_result={},
            all_blocks=[], stitched_blocks=[], errors=[], execution_metadata={},
        )

        with patch("apps.ai_classroom.enrichment_nodes.active_prompt") as mock_prompt, \
             patch("apps.ai_classroom.enrichment_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.ai_classroom.enrichment_nodes.validate_stage_output"), \
             patch("apps.ai_classroom.enrichment_nodes.log_llm_call"):
            mock_prompt.return_value = MagicMock(version="v1", template="Fill gaps")
            mock_get_llm.return_value = MockLLMProvider()
            result = gap_fill_node(state)

            self.assertIn("fill_result", result)

    def test_citation_stitch_node_stitches_refs(self):
        user_chunks = [{"chunk_id": "c1", "content": "Dijkstra", "source_type": "note",
                        "document_id": "doc-1", "page_start": 1, "page_end": 1, "revision_ids": []}]
        reference_chunks = [{"chunk_id": "ref-1", "content": "Complexity", "source_type": "reference",
                              "document_id": "ref-doc", "page_start": 1, "page_end": 1, "revision_ids": []}]
        state = EnrichmentState(
            document_id="doc-1", job_id="job-1",
            user_chunks=user_chunks, reference_chunks=reference_chunks,
            evidence_payload={},
            draft_result={"blocks": [{"block_type": "overview", "content": "test", "generation_method": "llm",
                                      "source_chunk_ids": ["c1"]}]},
            gaps_result={"gaps": []}, fill_result={"blocks": []},
            all_blocks=[], stitched_blocks=[], errors=[], execution_metadata={},
        )

        result = citation_stitch_node(state)
        self.assertEqual(len(result["stitched_blocks"]), 1)
        self.assertEqual(result["stitched_blocks"][0]["refs"][0]["chunk_id"], "c1")

    def test_evidence_verification_node_classifies(self):
        with patch("apps.ai_classroom.services.EvidenceVerifier") as mock_verifier:
            mock_verifier.verify.return_value = ("supported", 0.9)
            state = EnrichmentState(
                document_id="doc-1", job_id="job-1",
                user_chunks=[], reference_chunks=[], evidence_payload={},
                draft_result={}, gaps_result={}, fill_result={},
                all_blocks=[], stitched_blocks=[
                    {"index": 0, "block_type": "overview", "content": "test", "refs": [{"chunk_id": "c1"}]}
                ], errors=[], execution_metadata={},
            )

            result = evidence_verification_node(state)
            self.assertEqual(result["stitched_blocks"][0]["status"], "supported")
            self.assertEqual(result["stitched_blocks"][0]["score"], 0.9)

    def test_format_output_node_passthrough(self):
        state = EnrichmentState(
            document_id="doc-1", job_id="job-1",
            user_chunks=[], reference_chunks=[], evidence_payload={},
            draft_result={"blocks": [{"type": "t"}]},
            gaps_result={"gaps": []},
            fill_result={"blocks": [{"type": "f"}]},
            all_blocks=[{"type": "a"}], stitched_blocks=[{"type": "s"}],
            errors=[], execution_metadata={},
        )

        result = format_output_node(state)
        self.assertEqual(result["all_blocks"], [{"type": "a"}])
        self.assertEqual(result["stitched_blocks"], [{"type": "s"}])


class TestEnrichmentGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_enrichment_graph()
        self.assertIsNotNone(graph)

    def test_branch_after_gap_detection_with_gaps(self):
        state = {"gaps_result": {"gaps": [{"topic": "x"}]}}
        self.assertEqual(_branch_after_gap_detection(state), "gap_fill")

    def test_branch_after_gap_detection_without_gaps(self):
        state = {"gaps_result": {"gaps": []}}
        self.assertEqual(_branch_after_gap_detection(state), "citation_stitch")

    def test_branch_after_gap_detection_empty_gaps_result(self):
        state = {"gaps_result": {}}
        self.assertEqual(_branch_after_gap_detection(state), "citation_stitch")
