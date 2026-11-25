"""Phase 5 Verification graph tests."""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from ai.langgraph.graphs.verification_graph import build_verification_graph, invoke_verification_graph
from ai.langgraph.state.verification_state import VerificationState
from apps.ai_classroom.services import EvidenceVerifier
from providers.base import StructuredLLMResult


class TestVerificationGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_verification_graph()
        self.assertIsNotNone(graph)

    @patch("ai.langgraph.nodes.verification_nodes.EvidenceVerifier._classify")
    def test_graph_invocation(self, mock_classify):
        mock_classify.return_value = ("supported", 0.9)
        from ai.langgraph.graphs.verification_graph import invoke_verification_graph

        state = VerificationState(
            content="test content",
            cited_contents=["evidence 1", "evidence 2"],
            verification_status="not_verified",
            verification_score=0.0,
            errors=[],
            execution_metadata={},
        )

        result = invoke_verification_graph(state)
        self.assertEqual(result["verification_status"], "supported")
        self.assertEqual(result["verification_score"], 0.9)

    def test_fast_path_high_and_very_low_skip_llm(self):
        with patch("providers.registry.get_llm_provider") as mock_get_llm:
            status_hi, score_hi = EvidenceVerifier._classify(
                "Dijkstra computes shortest paths in weighted graphs",
                ["Dijkstra computes shortest paths in weighted graphs"],
            )
            status_lo, score_lo = EvidenceVerifier._classify(
                "Dijkstra computes shortest paths in weighted graphs",
                ["Photosynthesis converts solar energy into glucose"],
            )
        mock_get_llm.assert_not_called()
        self.assertEqual(status_hi, "supported")
        self.assertGreaterEqual(score_hi, 0.60)
        self.assertEqual(status_lo, "unsupported")
        self.assertLess(score_lo, 0.15)

    def test_borderline_band_invokes_semantic_judge_and_handles_fallback(self):
        claim = "Backpropagation computes chain-rule gradients across neural layers"
        evidence = ["Training adjusts weights using gradients across layers"]
        # Lexical overlap: {"gradients", "across", "layers"} -> 3/8 = 0.375 (borderline 0.15..0.60)

        mock_llm = MagicMock()
        mock_llm.generate_structured.return_value = StructuredLLMResult(
            data={"verdict": "ENTAILED", "rationale": "Semantically equivalent"},
            model="test-judge",
        )
        with patch("providers.registry.get_llm_provider", return_value=mock_llm):
            status_entailed, score_entailed = EvidenceVerifier._classify(claim, evidence)
        mock_llm.generate_structured.assert_called_once()
        self.assertEqual(status_entailed, "supported")
        self.assertGreaterEqual(score_entailed, 0.80)

        # Contradiction verdict overrides moderate lexical overlap cleanly
        mock_llm.generate_structured.return_value = StructuredLLMResult(
            data={"verdict": "CONTRADICTED", "rationale": "Negates evidence"},
            model="test-judge",
        )
        with patch("providers.registry.get_llm_provider", return_value=mock_llm):
            status_contra, score_contra = EvidenceVerifier._classify(claim, evidence)
        self.assertEqual(status_contra, "unsupported")
        self.assertLessEqual(score_contra, 0.15)

        # Provider error falls back cleanly to lexical partial threshold (0.375 >= 0.30)
        mock_llm.generate_structured.side_effect = RuntimeError("provider unavailable")
        with patch("providers.registry.get_llm_provider", return_value=mock_llm):
            status_fallback, _ = EvidenceVerifier._classify(claim, evidence)
        self.assertEqual(status_fallback, "partially_supported")

    def test_verification_graph_end_to_end_tiered_borderline(self):
        mock_llm = MagicMock()
        mock_llm.generate_structured.return_value = StructuredLLMResult(
            data={"verdict": "ENTAILED", "rationale": "Supported by paraphrase"},
            model="test-judge",
        )
        state = VerificationState(
            content="Backpropagation computes chain-rule gradients across neural layers",
            cited_contents=["Training adjusts weights using gradients across layers"],
            verification_status="not_verified",
            verification_score=0.0,
            errors=[],
            execution_metadata={},
        )
        with patch("providers.registry.get_llm_provider", return_value=mock_llm):
            result = invoke_verification_graph(state)
        self.assertEqual(result["verification_status"], "supported")
        self.assertGreaterEqual(result["verification_score"], 0.80)
