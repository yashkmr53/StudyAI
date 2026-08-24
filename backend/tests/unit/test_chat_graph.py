"""Phase 12 LangGraph chat graph tests."""
from unittest.mock import patch, MagicMock
import json

from django.test import TestCase, override_settings

from ai.langgraph.state.chat_state import ChatState
from ai.schemas.chat import ChatAnswer
from ai.langgraph.graphs.chat_graph import build_chat_graph
from apps.chat.langgraph_nodes import (
    retrieve_node,
    evidence_selection_node,
    answer_generation_node,
    citation_verification_node,
    format_response_node,
)


class MockLLMProvider:
    model_name = "mock-gpt"
    name = "mock"

    def generate_structured(self, *, prompt=None, schema=None, request_id=None):
        marker = "EVIDENCE_JSON:"
        evidence = {}
        if prompt and prompt.user and marker in prompt.user:
            try:
                evidence = json.loads(prompt.user.split(marker, 1)[1])
            except Exception:
                pass

        chunks = evidence.get("evidence", [])
        if not chunks:
            return type("R", (), {
                "data": {
                    "answer": "I could not find anything about that.",
                    "cited_chunk_ids": [],
                },
                "model": "mock-gpt",
                "prompt_name": prompt.name if prompt else "chat",
                "prompt_version": prompt.version if prompt else "v1",
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            })()

        top = chunks[0]
        answer = f"Based on your materials: {top['content'][:280]}"
        return type("R", (), {
            "data": {
                "answer": answer,
                "cited_chunk_ids": [c["chunk_id"] for c in chunks],
            },
            "model": "mock-gpt",
            "prompt_name": prompt.name if prompt else "chat",
            "prompt_version": prompt.version if prompt else "v1",
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        })()


class MockEvidence:
    def __init__(self, chunk_id, content, source_type="note", document_id="doc-1", page_start=1, page_end=1):
        self.chunk_id = chunk_id
        self.content_snippet = content
        self.source_type = source_type
        self.document_id = document_id
        self.page_start = page_start
        self.page_end = page_end
        self.rrf_score = 1.0

    def as_dict(self):
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_type": self.source_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "snippet": self.content_snippet,
            "scores": {
                "dense": None,
                "keyword": None,
                "rrf": round(self.rrf_score, 6),
            },
        }


class TestChatGraphNodes(TestCase):
    def test_retrieve_node_returns_evidence(self):
        evidence = [
            MockEvidence("chunk-1", "Dijkstra computes shortest paths"),
            MockEvidence("chunk-2", "Graph algorithms are important"),
        ]
        state = ChatState(
            user_request="What does Dijkstra compute?",
            profile_id="profile-1",
            subject_id=None,
            session_id="session-1",
            retrieved_evidence=[],
            selected_evidence=[],
            answer="",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            retry_count=0,
            errors=[],
            execution_metadata={},
        )

        with patch("apps.chat.langgraph_nodes.ChatSession.objects.select_related") as mock_qs, \
             patch("apps.chat.langgraph_nodes.RetrievalService.search") as mock_search, \
             patch("apps.chat.langgraph_nodes.log_retrieval"):
            mock_session = MagicMock()
            mock_session.profile_id = "profile-1"
            mock_session.subject = None
            mock_session.pk = "session-1"
            mock_qs.return_value.get.return_value = mock_session
            mock_search.return_value = evidence

            result = retrieve_node(state)

            self.assertEqual(len(result["retrieved_evidence"]), 2)
            self.assertEqual(result["retrieved_evidence"][0]["chunk_id"], "chunk-1")

    def test_evidence_selection_node_passthrough(self):
        evidence = [{"chunk_id": "c1", "snippet": "test"}]
        state = ChatState(
            user_request="test",
            profile_id="p1",
            subject_id=None,
            session_id="s1",
            retrieved_evidence=evidence,
            selected_evidence=[],
            answer="",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            retry_count=0,
            errors=[],
            execution_metadata={},
        )

        result = evidence_selection_node(state)
        self.assertEqual(result["selected_evidence"], evidence)

    def test_answer_generation_node(self):
        evidence = [{"chunk_id": "c1", "snippet": "Dijkstra computes shortest paths",
                     "source_type": "note", "document_id": "doc-1",
                     "page_start": 1, "page_end": 1,
                     "scores": {"dense": 1.0, "keyword": 1.0, "rrf": 1.0}}]
        state = ChatState(
            user_request="What does Dijkstra compute?",
            profile_id="p1",
            subject_id=None,
            session_id="s1",
            retrieved_evidence=evidence,
            selected_evidence=evidence,
            answer="",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            retry_count=0,
            errors=[],
            execution_metadata={},
            cited_contents=[],
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = answer_generation_node(state)

            self.assertIn("answer", result)
            self.assertIn("citations", result)
            self.assertIn("cited_contents", result)
            self.assertEqual(len(result["citations"]), 1)
            self.assertEqual(result["citations"][0]["chunk_id"], "c1")

    def test_citation_verification_node(self):
        state = ChatState(
            user_request="test",
            profile_id="p1",
            subject_id=None,
            session_id="s1",
            retrieved_evidence=[],
            selected_evidence=[],
            answer="Dijkstra computes shortest paths",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            retry_count=0,
            errors=[],
            execution_metadata={},
            cited_contents=["Dijkstra computes shortest paths in weighted graphs"],
        )

        result = citation_verification_node(state)
        self.assertIn("verification_status", result)
        self.assertIn(result["verification_status"], ["supported", "partially_supported", "unsupported"])

    def test_format_response_node(self):
        state = ChatState(
            user_request="test",
            profile_id="p1",
            subject_id=None,
            session_id="s1",
            retrieved_evidence=[],
            selected_evidence=[],
            answer="test answer",
            citations=[{"chunk_id": "c1"}],
            verification_status="supported",
            verification_score=0.9,
            retry_count=0,
            errors=[],
            execution_metadata={},
        )

        result = format_response_node(state)
        self.assertEqual(result["answer"], "test answer")
        self.assertEqual(result["verification_status"], "supported")


class TestChatGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_chat_graph()
        self.assertIsNotNone(graph)

    @patch("ai.langgraph.graphs.chat_graph.retrieve_node")
    @patch("ai.langgraph.graphs.chat_graph.evidence_selection_node")
    @patch("ai.langgraph.graphs.chat_graph.answer_generation_node")
    @patch("ai.langgraph.graphs.chat_graph._run_verification")
    @patch("ai.langgraph.graphs.chat_graph.format_response_node")
    def test_graph_linear_flow(self, mock_format, mock_verify, mock_generate, mock_select, mock_retrieve):
        from ai.langgraph.graphs.chat_graph import _branch_after_verification

        mock_retrieve.return_value = {"retrieved_evidence": [], "selected_evidence": []}
        mock_select.return_value = {"selected_evidence": []}
        mock_generate.return_value = {"answer": "test", "citations": [], "cited_contents": []}
        mock_verify.return_value = {"verification_status": "supported", "verification_score": 0.9}
        mock_format.return_value = {"answer": "test", "verification_status": "supported"}

        self.assertEqual(_branch_after_verification({"verification_status": "supported"}), "format_response")
        self.assertEqual(_branch_after_verification({"verification_status": "partially_supported"}), "format_response")
        self.assertEqual(_branch_after_verification({"verification_status": "unsupported", "retry_count": 1}), "format_response")
        self.assertEqual(_branch_after_verification({"verification_status": "unsupported", "retry_count": 0}), "retry_answer")
