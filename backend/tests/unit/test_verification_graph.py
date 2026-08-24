"""Phase 5 Verification graph tests."""
from unittest.mock import patch

from django.test import TestCase

from ai.langgraph.graphs.verification_graph import build_verification_graph
from ai.langgraph.state.verification_state import VerificationState


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
