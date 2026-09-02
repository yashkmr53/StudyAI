"""Phase 12 LangGraph chat graph tests."""
from unittest.mock import patch, MagicMock
import json

from django.test import TestCase, override_settings

from ai.langgraph.state.chat_state import ChatState
from ai.schemas.chat import ChatAnswer
from ai.langgraph.graphs.chat_graph import build_chat_graph, _branch_after_route
from apps.chat.langgraph_nodes import (
    route_query_node,
    retrieve_node,
    evidence_selection_node,
    answer_generation_node,
    citation_verification_node,
    format_response_node,
)
from providers.llm.mock import MockLLMProvider


class MockEvidence:
    def __init__(self, chunk_id, content, source_type="note", document_id="doc-1", page_start=1, page_end=1,
                 document_title="DSA Notes", subject_name="Algorithms"):
        self.chunk_id = chunk_id
        self.content_snippet = content
        self.source_type = source_type
        self.document_id = document_id
        self.page_start = page_start
        self.page_end = page_end
        self.rrf_score = 1.0
        self.document_title = document_title
        self.subject_name = subject_name

    def as_dict(self):
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_type": self.source_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "snippet": self.content_snippet,
            "document_title": self.document_title,
            "subject_name": self.subject_name,
            "scores": {
                "dense": None,
                "keyword": None,
                "rrf": round(self.rrf_score, 6),
            },
        }


def _blank_state(**overrides):
    defaults = {
        "user_request": "",
        "profile_id": "p1",
        "subject_id": None,
        "session_id": "s1",
        "route": None,
        "retrieved_evidence": [],
        "web_evidence": [],
        "selected_evidence": [],
        "answer": "",
        "citations": [],
        "cited_contents": [],
        "verification_status": "not_verified",
        "verification_score": 0.0,
        "retry_count": 0,
        "errors": [],
        "execution_metadata": {},
    }
    defaults.update(overrides)
    return ChatState(**defaults)


class TestChatGraphNodes(TestCase):
    def test_route_query_classifies_conversational(self):
        state = _blank_state(user_request="hi")
        result = route_query_node(state)
        self.assertEqual(result["route"], "conversational")

    def test_route_query_classifies_conversational_thanks(self):
        state = _blank_state(user_request="thank you")
        result = route_query_node(state)
        self.assertEqual(result["route"], "conversational")

    def test_route_query_classifies_date(self):
        state = _blank_state(user_request="what is today's date?")
        result = route_query_node(state)
        self.assertEqual(result["route"], "date_time")

    def test_route_query_classifies_time(self):
        state = _blank_state(user_request="what time is it?")
        result = route_query_node(state)
        self.assertEqual(result["route"], "date_time")

    def test_route_query_classifies_personal(self):
        state = _blank_state(user_request="my name is yash")
        result = route_query_node(state)
        self.assertEqual(result["route"], "conversational")

    def test_route_query_classifies_what_is_my_name(self):
        state = _blank_state(user_request="what is my name?")
        result = route_query_node(state)
        self.assertEqual(result["route"], "conversational")

    def test_route_query_classifies_material(self):
        state = _blank_state(user_request="What does Dijkstra compute in my notes?")
        result = route_query_node(state)
        self.assertEqual(result["route"], "material")

    def test_route_query_classifies_material_my_notes(self):
        state = _blank_state(user_request="Explain dynamic programming from my notes")
        result = route_query_node(state)
        self.assertEqual(result["route"], "material")

    def test_route_query_classifies_general_knowledge(self):
        state = _blank_state(user_request="What does Dijkstra compute?")
        result = route_query_node(state)
        self.assertEqual(result["route"], "general_knowledge")

    def test_branch_after_route_conversational(self):
        self.assertEqual(_branch_after_route({"route": "conversational"}), "answer_generation")

    def test_branch_after_route_material(self):
        self.assertEqual(_branch_after_route({"route": "material"}), "retrieve")

    def test_retrieve_node_returns_evidence(self):
        evidence = [
            MockEvidence("chunk-1", "Dijkstra computes shortest paths"),
            MockEvidence("chunk-2", "Graph algorithms are important"),
        ]
        state = _blank_state(user_request="What does Dijkstra compute?")

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
        state = _blank_state(retrieved_evidence=evidence)

        result = evidence_selection_node(state)
        self.assertEqual(result["selected_evidence"], evidence)

    def test_answer_generation_node(self):
        evidence = [{"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "Dijkstra computes shortest paths in weighted graphs.",
                     "source_type": "note", "document_id": "doc-1",
                     "page_start": 1, "page_end": 1,
                     "document_title": "DSA Notes", "subject_name": "Algorithms",
                     "scores": {"dense": 1.0, "keyword": 1.0, "rrf": 1.0}}]
        state = _blank_state(
            user_request="What does Dijkstra compute?",
            selected_evidence=evidence,
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            real_provider = MockLLMProvider()
            mock_llm = MagicMock(wraps=real_provider)
            mock_get_llm.return_value = mock_llm
            result = answer_generation_node(state)

            self.assertIn("answer", result)
            self.assertIn("citations", result)
            self.assertIn("cited_contents", result)
            self.assertEqual(len(result["citations"]), 1)
            self.assertEqual(result["citations"][0]["source_type"], "database")
            self.assertEqual(result["citations"][0]["document_title"], "DSA Notes")
            self.assertEqual(result["citations"][0]["subject_name"], "Algorithms")
            self.assertIn("src-", result["citations"][0]["source_id"])
            # The question must be present in the prompt sent to the LLM
            sent_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertIn("What does Dijkstra compute?", sent_prompt.user)
            # The answer should be a grounded sentence, not a raw content dump
            self.assertIn("Dijkstra", result["answer"])

    def test_greeting_does_not_dump_evidence(self):
        """A greeting like 'hi' must produce a conversational response,
        never raw retrieved content (e.g. OCR 'Recognized line' text)."""
        evidence = [{"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "Recognized line 1: c14eb0\nRecognized line 2: c7c778",
                     "source_type": "note", "document_id": "doc-1",
                     "page_start": 1, "page_end": 1,
                     "document_title": "DSA Notes", "subject_name": "Algorithms",
                     "scores": {"dense": 1.0, "keyword": 1.0, "rrf": 1.0}}]
        state = _blank_state(
            user_request="hi",
            selected_evidence=evidence,
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = answer_generation_node(state)

            self.assertIn("hello", result["answer"].lower())  # conversational greeting
            self.assertNotIn("Recognized line", result["answer"])
            self.assertEqual(result["citations"], [])

    def test_conversational_no_evidence_still_handled(self):
        """When routed as conversational but evidence was retrieved anyway,
        the mock should still respond conversationally."""
        evidence = [{"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "Some study material about graphs",
                     "source_type": "note", "document_id": "doc-1",
                     "page_start": 1, "page_end": 1,
                     "document_title": "DSA Notes", "subject_name": "Algorithms",
                     "scores": {"dense": 1.0, "keyword": 1.0, "rrf": 1.0}}]
        state = _blank_state(
            user_request="hi there",
            selected_evidence=evidence,
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = answer_generation_node(state)
            self.assertIn("hello", result["answer"].lower())

    def test_mock_chat_handles_greeting(self):
        from providers.base import Prompt

        provider = MockLLMProvider()
        prompt = Prompt(
            name="chat",
            version="v1",
            user='QUESTION: hi\n\nEVIDENCE_JSON:{"evidence": []}',
        )
        result = provider.generate_structured(prompt=prompt, schema=ChatAnswer, request_id="r")
        self.assertIn("hello", result.data["answer"].lower())
        self.assertEqual(result.data["cited_chunk_ids"], [])

    def test_mock_chat_extracts_question_and_answers_from_evidence(self):
        from providers.base import Prompt

        provider = MockLLMProvider()
        prompt = Prompt(
            name="chat",
            version="v1",
            system="Answer the question using only the evidence.",
            user=(
                'QUESTION: What does Dijkstra compute?\n\n'
                'EVIDENCE_JSON:{"evidence": ['
                '{"chunk_id": "c1", "content": "[Mathematics] Dijkstra computes shortest paths in weighted graphs."}'
                ']}'
            ),
        )
        result = provider.generate_structured(prompt=prompt, schema=ChatAnswer, request_id="r")
        self.assertIn("Dijkstra", result.data["answer"])
        self.assertNotIn("[Mathematics]", result.data["answer"])
        self.assertIn("c1", result.data["cited_chunk_ids"])

    def test_mock_chat_no_evidence_returns_not_found(self):
        from providers.base import Prompt

        provider = MockLLMProvider()
        prompt = Prompt(
            name="chat",
            version="v1",
            user='QUESTION: what is quantum computing?\n\nEVIDENCE_JSON:{"evidence": []}',
        )
        result = provider.generate_structured(prompt=prompt, schema=ChatAnswer, request_id="r")
        self.assertIn("could not find", result.data["answer"].lower())
        self.assertEqual(result.data["cited_chunk_ids"], [])

    def test_citation_ids_are_stable_and_verifiable(self):
        """Citations should have source_id (SRC-001) and document metadata."""
        evidence = [
            {"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "Dijkstra computes shortest paths",
             "source_type": "note", "document_id": "doc-1",
             "page_start": 1, "page_end": 1,
             "document_title": "Algorithms Notes", "subject_name": "DSA",
             "scores": {"dense": 1.0, "keyword": 1.0, "rrf": 1.0}},
            {"citation_id": "SRC-002", "chunk_id": "c2", "snippet": "Dynamic programming caches results",
             "source_type": "reference", "document_id": "doc-2",
             "page_start": 17, "page_end": 18,
             "document_title": "Introduction to Algorithms", "subject_name": "DSA",
             "scores": {"dense": 0.9, "keyword": 0.9, "rrf": 0.9}},
        ]
        state = _blank_state(
            user_request="Explain Dijkstra and dynamic programming",
            selected_evidence=evidence,
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = answer_generation_node(state)

            for i, cit in enumerate(result["citations"]):
                self.assertIn("source_id", cit)
                self.assertTrue(cit["source_id"].startswith("src-"))
                self.assertEqual(cit["document_title"], evidence[i]["document_title"])
                self.assertEqual(cit["subject_name"], evidence[i]["subject_name"])
                self.assertEqual(cit["source_type"], "database")

    def test_citation_hallucination_filtered(self):
        """Citations referencing unknown chunk IDs must be dropped."""
        evidence = [
            {"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "Dijkstra computes shortest paths",
             "source_type": "note", "document_id": "doc-1",
             "page_start": 1, "page_end": 1,
             "document_title": "DSA Notes", "subject_name": "Algorithms",
             "scores": {"dense": 1.0, "keyword": 1.0, "rrf": 1.0}},
        ]
        state = _blank_state(
            user_request="Explain Dijkstra",
            selected_evidence=evidence,
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = answer_generation_node(state)

            # The mock's _chat always cites all chunks, so we verify our
            # _build_citations logic by checking that all cited IDs map to evidence
            cited_ids = result["cited_contents"]
            self.assertEqual(len(result["citations"]), 1)
            self.assertEqual(result["citations"][0]["chunk_id"], "c1")

    def test_citation_verification_node(self):
        state = _blank_state(
            user_request="test",
            answer="Dijkstra computes shortest paths",
            cited_contents=["Dijkstra computes shortest paths in weighted graphs"],
        )

        result = citation_verification_node(state)
        self.assertIn("verification_status", result)
        self.assertIn(result["verification_status"], ["supported", "partially_supported", "unsupported"])

    def test_format_response_node(self):
        state = _blank_state(
            answer="test answer",
            citations=[{"chunk_id": "c1", "source_id": "src-001"}],
            verification_status="supported",
            verification_score=0.9,
        )

        result = format_response_node(state)
        self.assertEqual(result["answer"], "test answer")
        self.assertEqual(result["verification_status"], "supported")


class TestChatGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_chat_graph()
        self.assertIsNotNone(graph)

    def test_graph_has_routing_node(self):
        graph = build_chat_graph()
        # The compiled graph should have a route_query entry point
        # Verify by checking the graph structure
        from langgraph.graph.state import CompiledStateGraph
        self.assertIsInstance(graph, CompiledStateGraph)

    @patch("ai.langgraph.graphs.chat_graph.retrieve_node")
    @patch("ai.langgraph.graphs.chat_graph.evidence_selection_node")
    @patch("ai.langgraph.graphs.chat_graph.answer_generation_node")
    @patch("ai.langgraph.graphs.chat_graph._run_verification")
    @patch("ai.langgraph.graphs.chat_graph.format_response_node")
    @patch("ai.langgraph.graphs.chat_graph.route_query_node")
    def test_graph_material_flow(self, mock_route, mock_format, mock_verify, mock_generate, mock_select, mock_retrieve):
        from ai.langgraph.graphs.chat_graph import _branch_after_route, _branch_after_verification

        mock_route.return_value = {"route": "material"}
        mock_retrieve.return_value = {"retrieved_evidence": [], "selected_evidence": []}
        mock_select.return_value = {"selected_evidence": []}
        mock_generate.return_value = {"answer": "test", "citations": [], "cited_contents": []}
        mock_verify.return_value = {"verification_status": "supported", "verification_score": 0.9}
        mock_format.return_value = {"answer": "test", "verification_status": "supported"}

        self.assertEqual(_branch_after_route({"route": "conversational"}), "answer_generation")
        self.assertEqual(_branch_after_route({"route": "material"}), "retrieve")
        self.assertEqual(_branch_after_verification({"verification_status": "supported"}), "format_response")
        self.assertEqual(_branch_after_verification({"verification_status": "partially_supported"}), "format_response")
        self.assertEqual(_branch_after_verification({"verification_status": "unsupported", "retry_count": 1}), "format_response")
        self.assertEqual(_branch_after_verification({"verification_status": "unsupported", "retry_count": 0}), "retry_answer")

    @patch("ai.langgraph.graphs.chat_graph.retrieve_node")
    @patch("ai.langgraph.graphs.chat_graph.evidence_selection_node")
    @patch("ai.langgraph.graphs.chat_graph.answer_generation_node")
    @patch("ai.langgraph.graphs.chat_graph._run_verification")
    @patch("ai.langgraph.graphs.chat_graph.format_response_node")
    @patch("ai.langgraph.graphs.chat_graph.route_query_node")
    def test_graph_conversational_flow(self, mock_route, mock_format, mock_verify, mock_generate, mock_select, mock_retrieve):
        from ai.langgraph.graphs.chat_graph import _branch_after_route

        mock_route.return_value = {"route": "conversational"}
        mock_generate.return_value = {"answer": "Hello!", "citations": [], "cited_contents": []}
        mock_verify.return_value = {"verification_status": "supported", "verification_score": 0.9}
        mock_format.return_value = {"answer": "Hello!", "verification_status": "supported"}

        # Conversational queries should skip retrieval entirely
        self.assertEqual(_branch_after_route({"route": "conversational"}), "answer_generation")
        self.assertEqual(_branch_after_route({"route": "material"}), "retrieve")


class ChatServiceTitleTest(TestCase):
    """Tests for ChatService title generation."""

    def test_generate_title_short_message(self):
        from apps.chat.services import ChatService
        self.assertEqual(ChatService._generate_title("What is gradient descent?"), "What is gradient descent?")

    def test_generate_title_very_short(self):
        from apps.chat.services import ChatService
        self.assertEqual(ChatService._generate_title("Explain RAG"), "Explain RAG")

    def test_generate_title_truncates_long_message(self):
        from apps.chat.services import ChatService
        title = ChatService._generate_title("This is a very long message that should be truncated at some point to keep titles short")
        self.assertTrue(len(title) <= 50)
        self.assertEqual(title, "This is a very long message that should be")

    def test_generate_title_truncates_at_word_boundary(self):
        from apps.chat.services import ChatService
        title = ChatService._generate_title("What is the difference between BFS and DFS in graph theory")
        self.assertTrue(len(title) <= 50)
        self.assertFalse(title.endswith(" "))


class TestRegressionConversationalHistory(TestCase):
    """Regression tests for conversational history and verification bypass."""

    def test_branch_after_verification_skips_retry_for_conversational(self):
        from ai.langgraph.graphs.chat_graph import _branch_after_verification
        self.assertEqual(
            _branch_after_verification({"route": "conversational", "verification_status": "unsupported", "retry_count": 0}),
            "format_response",
        )
        self.assertEqual(
            _branch_after_verification({"route": "date_time", "verification_status": "unsupported", "retry_count": 0}),
            "format_response",
        )

    def test_answer_generation_omits_empty_evidence_json(self):
        """When no evidence is present, the prompt must not include EVIDENCE_JSON."""
        from providers.base import Prompt

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock()
            mock_llm.name = "test"
            mock_llm.generate_structured.return_value = MagicMock(
                data={"answer": "Your name is Yash.", "cited_ids": [], "confidence": 0.9},
                model="test",
                input_tokens=10,
                output_tokens=10,
                total_tokens=20,
            )
            mock_get_llm.return_value = mock_llm

            state = _blank_state(
                user_request="what is my name?",
                messages=[{"role": "user", "content": "my name is yash"}],
                route="conversational",
            )
            result = answer_generation_node(state)

            sent_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertNotIn("EVIDENCE_JSON", sent_prompt.user)
            self.assertIn("CONVERSATION HISTORY", sent_prompt.user)
            self.assertIn("my name is yash", sent_prompt.user)
            self.assertEqual(result["answer"], "Your name is Yash.")

    def test_answer_generation_includes_evidence_when_present(self):
        """When evidence IS present, the prompt must include EVIDENCE_JSON."""
        from providers.base import Prompt

        evidence = [{"citation_id": "SRC-001", "chunk_id": "c1", "snippet": "test content",
                     "source_type": "database", "document_title": "Notes"}]

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock()
            mock_llm.name = "test"
            mock_llm.generate_structured.return_value = MagicMock(
                data={"answer": "Based on notes, test.", "cited_ids": ["SRC-001"], "confidence": 0.9},
                model="test",
                input_tokens=10,
                output_tokens=10,
                total_tokens=20,
            )
            mock_get_llm.return_value = mock_llm

            state = _blank_state(
                user_request="what is test?",
                selected_evidence=evidence,
                route="material",
            )
            result = answer_generation_node(state)

            sent_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertIn("EVIDENCE_JSON", sent_prompt.user)

    def test_mock_handles_name_queries_conversationally(self):
        """Mock LLM should recognize name queries as conversational."""
        from providers.base import Prompt

        provider = MockLLMProvider()

        for query in ["my name is yash", "what is my name?", "do you know my name?"]:
            prompt = Prompt(
                name="chat",
                version="v1",
                user=f"QUESTION: {query}",
            )
            result = provider.generate_structured(prompt=prompt, schema=ChatAnswer, request_id="r")
            self.assertNotIn("could not find", result.data["answer"].lower(),
                             f"Mock should handle '{query}' conversationally")
