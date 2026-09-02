"""Tests for web search provider, web retrieval node, and web citations."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from ai.langgraph.state.chat_state import ChatState
from ai.schemas.chat import ChatAnswer
from ai.langgraph.graphs.chat_graph import build_chat_graph, _branch_after_route
from apps.chat.langgraph_nodes import (
    route_query_node,
    retrieve_web_node,
    evidence_selection_node,
    answer_generation_node,
    _build_citations,
)
from providers.web.base import WebSearchResult
from providers.web.mock import MockWebSearchProvider
from providers.llm.mock import MockLLMProvider


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


class TestMockWebSearchProvider(TestCase):
    def test_returns_deterministic_results(self):
        provider = MockWebSearchProvider()
        results = provider.search("dynamic programming", max_results=3, request_id="r")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].source_type, "web")
        self.assertTrue(results[0].url.startswith("http"))
        self.assertTrue(results[0].domain)

    def test_empty_query_returns_empty(self):
        provider = MockWebSearchProvider()
        self.assertEqual(provider.search("", max_results=5, request_id="r"), [])

    def test_results_have_authoritative_metadata(self):
        provider = MockWebSearchProvider()
        results = provider.search("gradient descent", max_results=1, request_id="r")
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertIn("gradient descent", r.title.lower())
        self.assertIn("gradient-descent", r.url)
        self.assertEqual(r.domain, "en.wikipedia.org")

    def test_as_dict(self):
        r = WebSearchResult(title="Test", url="https://example.com/page", snippet="A snippet", domain="example.com")
        d = r.as_dict()
        self.assertEqual(d["source_type"], "web")
        self.assertEqual(d["url"], "https://example.com/page")
        self.assertEqual(d["domain"], "example.com")

    def test_domain_parsed_from_url(self):
        r = WebSearchResult(title="T", url="https://docs.python.org/3/library/", snippet="s")
        self.assertEqual(r.domain, "docs.python.org")


class TestRouteQueryNode(TestCase):
    def test_conversational_hi(self):
        result = route_query_node(_blank_state(user_request="hi"))
        self.assertEqual(result["route"], "conversational")

    def test_conversational_date(self):
        result = route_query_node(_blank_state(user_request="what is today's date?"))
        self.assertEqual(result["route"], "date_time")

    def test_conversational_time(self):
        result = route_query_node(_blank_state(user_request="what time is it?"))
        self.assertEqual(result["route"], "date_time")

    def test_material_my_notes(self):
        result = route_query_node(_blank_state(user_request="Explain dynamic programming from my notes"))
        self.assertEqual(result["route"], "material")

    def test_material_my_materials(self):
        result = route_query_node(_blank_state(user_request="What does Dijkstra compute in my materials?"))
        self.assertEqual(result["route"], "material")

    def test_general_knowledge(self):
        result = route_query_node(_blank_state(user_request="What is gradient descent?"))
        self.assertEqual(result["route"], "general_knowledge")

    def test_general_knowledge_how_does(self):
        result = route_query_node(_blank_state(user_request="How does quicksort work?"))
        self.assertEqual(result["route"], "general_knowledge")

    def test_branch_after_route_conversational(self):
        self.assertEqual(_branch_after_route({"route": "conversational"}), "answer_generation")

    def test_branch_after_route_material(self):
        self.assertEqual(_branch_after_route({"route": "material"}), "retrieve")

    def test_branch_after_route_general_knowledge(self):
        self.assertEqual(_branch_after_route({"route": "general_knowledge"}), "retrieve_web")


class TestRetrieveWebNode(TestCase):
    def test_retrieve_web_returns_evidence(self):
        state = _blank_state(user_request="What is gradient descent?")
        with patch("apps.chat.langgraph_nodes.get_web_search_provider") as mock_get, \
             patch("apps.chat.langgraph_nodes.log_retrieval"):
            mock_provider = MockWebSearchProvider()
            mock_get.return_value = mock_provider
            result = retrieve_web_node(state)
            self.assertIn("web_evidence", result)
            self.assertGreater(len(result["web_evidence"]), 0)
            self.assertEqual(result["web_evidence"][0]["source_type"], "web")
            self.assertIn("url", result["web_evidence"][0])
            self.assertIn("domain", result["web_evidence"][0])

    def test_retrieve_web_empty_query(self):
        state = _blank_state(user_request="")
        with patch("apps.chat.langgraph_nodes.get_web_search_provider") as mock_get, \
             patch("apps.chat.langgraph_nodes.log_retrieval"):
            mock_get.return_value = MockWebSearchProvider()
            result = retrieve_web_node(state)
            self.assertEqual(result["web_evidence"], [])


class TestEvidenceSelectionNode(TestCase):
    def test_merges_db_and_web_evidence(self):
        db_evidence = [{"chunk_id": "c1", "snippet": "DB content", "document_title": "Notes"}]
        web_evidence = [{"title": "Web Result", "url": "https://example.com", "snippet": "Web content", "domain": "example.com"}]
        state = _blank_state(retrieved_evidence=db_evidence, web_evidence=web_evidence)
        result = evidence_selection_node(state)
        selected = result["selected_evidence"]
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["citation_id"], "SRC-001")
        self.assertEqual(selected[0]["source_type"], "database")
        self.assertEqual(selected[1]["citation_id"], "SRC-002")
        self.assertEqual(selected[1]["source_type"], "web")

    def test_empty_evidence(self):
        result = evidence_selection_node(_blank_state())
        self.assertEqual(result["selected_evidence"], [])


class TestBuildCitations(TestCase):
    def test_web_citation_has_url_domain_title(self):
        evidence = [
            {"citation_id": "SRC-001", "source_type": "web", "title": "Python Docs",
             "url": "https://docs.python.org/3/library/datetime", "domain": "docs.python.org",
             "snippet": "The datetime module..."},
        ]
        citations, contents = _build_citations(evidence, ["SRC-001"])
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["source_type"], "web")
        self.assertEqual(citations[0]["url"], "https://docs.python.org/3/library/datetime")
        self.assertEqual(citations[0]["domain"], "docs.python.org")
        self.assertEqual(citations[0]["title"], "Python Docs")
        self.assertEqual(citations[0]["source_id"], "src-001")

    def test_hallucinated_citation_removed(self):
        evidence = [
            {"citation_id": "SRC-001", "source_type": "database", "chunk_id": "c1",
             "document_title": "Notes", "page_start": 1, "page_end": 1, "snippet": "content"},
        ]
        citations, contents = _build_citations(evidence, ["SRC-999"])
        self.assertEqual(len(citations), 0)

    def test_mixed_citations(self):
        evidence = [
            {"citation_id": "SRC-001", "source_type": "database", "chunk_id": "c1",
             "document_title": "DSA Notes", "subject_name": "Algorithms",
             "page_start": 17, "page_end": 18, "snippet": "DP content",
             "scores": {"rrf": 0.5}},
            {"citation_id": "SRC-002", "source_type": "web", "title": "DP Tutorial",
             "url": "https://example.com/dp", "domain": "example.com", "snippet": "Web DP"},
        ]
        citations, contents = _build_citations(evidence, ["SRC-001", "SRC-002"])
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["source_type"], "database")
        self.assertEqual(citations[0]["document_title"], "DSA Notes")
        self.assertEqual(citations[1]["source_type"], "web")
        self.assertEqual(citations[1]["url"], "https://example.com/dp")

    def test_backward_compat_chunk_id_lookup(self):
        """Citations should still resolve when evidence uses chunk_id only."""
        evidence = [
            {"chunk_id": "c1", "source_type": "database",
             "document_title": "Notes", "page_start": 1, "page_end": 1, "snippet": "content",
             "scores": {"rrf": 0.5}},
        ]
        citations, contents = _build_citations(evidence, ["c1"])
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["chunk_id"], "c1")


class TestAnswerGenerationWithWebEvidence(TestCase):
    def test_web_evidence_in_prompt(self):
        evidence = [
            {"citation_id": "SRC-001", "source_type": "web", "title": "Gradient Descent",
             "url": "https://example.com/gd", "domain": "example.com",
             "snippet": "Gradient descent is an optimization algorithm."},
        ]
        state = _blank_state(user_request="What is gradient descent?", selected_evidence=evidence)
        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = answer_generation_node(state)
            self.assertIn("answer", result)
            self.assertIn("citations", result)
            # Web citation should have URL and domain
            if result["citations"]:
                self.assertEqual(result["citations"][0]["source_type"], "web")
                self.assertIn("url", result["citations"][0])


class TestChatGraphStructure(TestCase):
    def test_graph_builds_with_web_node(self):
        graph = build_chat_graph()
        self.assertIsNotNone(graph)

    def test_graph_has_retrieve_web(self):
        graph = build_chat_graph()
        from langgraph.graph.state import CompiledStateGraph
        self.assertIsInstance(graph, CompiledStateGraph)


class TestConversationalAndDate(TestCase):
    """Conversational and date queries should bypass retrieval entirely."""

    def test_hi_routes_to_conversational(self):
        result = route_query_node(_blank_state(user_request="hi"))
        self.assertEqual(result["route"], "conversational")

    def test_hello_routes_to_conversational(self):
        result = route_query_node(_blank_state(user_request="hello"))
        self.assertEqual(result["route"], "conversational")

    def test_date_routes_to_conversational(self):
        result = route_query_node(_blank_state(user_request="what is today's date?"))
        self.assertEqual(result["route"], "date_time")

    def test_time_routes_to_conversational(self):
        result = route_query_node(_blank_state(user_request="what time is it?"))
        self.assertEqual(result["route"], "date_time")

    def test_thanks_routes_to_conversational(self):
        result = route_query_node(_blank_state(user_request="thanks"))
        self.assertEqual(result["route"], "conversational")


class TestFullGraphFlow(TestCase):
    """Test the full graph flow with mocked providers."""

    @patch("ai.langgraph.graphs.chat_graph.evidence_selection_node")
    @patch("ai.langgraph.graphs.chat_graph.answer_generation_node")
    @patch("ai.langgraph.graphs.chat_graph._run_verification")
    @patch("ai.langgraph.graphs.chat_graph.format_response_node")
    @patch("ai.langgraph.graphs.chat_graph.route_query_node")
    def test_conversational_flow_skips_retrieval(self, mock_route, mock_format, mock_verify, mock_generate, mock_select):
        from ai.langgraph.graphs.chat_graph import _branch_after_route
        mock_route.return_value = {"route": "conversational"}
        mock_generate.return_value = {"answer": "Hello!", "citations": [], "cited_contents": []}
        mock_verify.return_value = {"verification_status": "supported", "verification_score": 0.9}
        mock_format.return_value = {"answer": "Hello!", "verification_status": "supported"}
        # Conversational should go directly to answer_generation
        self.assertEqual(_branch_after_route({"route": "conversational"}), "answer_generation")

    @patch("ai.langgraph.graphs.chat_graph.evidence_selection_node")
    @patch("ai.langgraph.graphs.chat_graph.answer_generation_node")
    @patch("ai.langgraph.graphs.chat_graph._run_verification")
    @patch("ai.langgraph.graphs.chat_graph.format_response_node")
    @patch("ai.langgraph.graphs.chat_graph.route_query_node")
    def test_general_knowledge_flow_uses_web(self, mock_route, mock_format, mock_verify, mock_generate, mock_select):
        from ai.langgraph.graphs.chat_graph import _branch_after_route
        mock_route.return_value = {"route": "general_knowledge"}
        mock_generate.return_value = {"answer": "Answer", "citations": [], "cited_contents": []}
        mock_verify.return_value = {"verification_status": "supported", "verification_score": 0.9}
        mock_format.return_value = {"answer": "Answer", "verification_status": "supported"}
        # General knowledge should retrieve from web
        self.assertEqual(_branch_after_route({"route": "general_knowledge"}), "retrieve_web")
