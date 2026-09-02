"""Integration tests for Bug fixes:
- Bug 1: No irrelevant citations on conversational/date responses
- Bug 2: Conversation history is used
- Bug 3: Date/time queries use runtime date/time
"""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from ai.langgraph.state.chat_state import ChatState
from ai.langgraph.graphs.chat_graph import build_chat_graph, _branch_after_route
from apps.chat.langgraph_nodes import (
    route_query_node,
    date_time_node,
    answer_generation_node,
    _build_citations,
)
from providers.llm.mock import MockLLMProvider


class TestBug1_CitationBehavior(TestCase):
    """Test that conversational/date responses have no citations."""

    def test_conversational_routes_to_answer_generation(self):
        """Conversational queries should skip retrieval entirely."""
        result = route_query_node(_blank_state(user_request="hi"))
        self.assertEqual(result["route"], "conversational")
        self.assertEqual(_branch_after_route(result), "answer_generation")

    def test_date_routes_to_date_time_node(self):
        """Date queries should use date_time node."""
        result = route_query_node(_blank_state(user_request="what is today's date?"))
        self.assertEqual(result["route"], "date_time")
        self.assertEqual(_branch_after_route(result), "date_time_node")

    def test_personal_statement_routes_to_conversational(self):
        """Personal statements like 'my name is yash' should be conversational."""
        result = route_query_node(_blank_state(user_request="my name is yash"))
        self.assertEqual(result["route"], "conversational")

    def test_date_time_node_provides_current_date(self):
        """Date/time node should inject current date into state."""
        result = date_time_node(_blank_state(user_request="what is today's date?"))
        self.assertIn("current_date", result)
        self.assertTrue(len(result["current_date"]) > 0)
        # Evidence should be empty
        self.assertEqual(result["retrieved_evidence"], [])
        self.assertEqual(result["web_evidence"], [])

    def test_build_citations_returns_empty_for_no_cited_ids(self):
        """If LLM doesn't cite anything, citations should be empty."""
        evidence = [
            {"citation_id": "SRC-001", "source_type": "database", "chunk_id": "c1",
             "document_title": "Notes", "page_start": 1, "page_end": 1, "snippet": "content",
             "scores": {"rrf": 0.5}},
        ]
        citations, contents = _build_citations(evidence, [])
        self.assertEqual(citations, [])
        self.assertEqual(contents, [])

    def test_build_citations_filters_hallucinated_ids(self):
        """Hallucinated citation IDs should be removed."""
        evidence = [
            {"citation_id": "SRC-001", "source_type": "database", "chunk_id": "c1",
             "document_title": "Notes", "page_start": 1, "page_end": 1, "snippet": "content",
             "scores": {"rrf": 0.5}},
        ]
        citations, contents = _build_citations(evidence, ["SRC-999"])
        self.assertEqual(citations, [])


class TestBug2_ConversationHistory(TestCase):
    """Test that conversation history is passed to the LLM."""

    def test_conversation_history_in_prompt(self):
        """The prompt should include conversation history."""
        messages = [
            {"role": "user", "content": "My name is Yash"},
            {"role": "assistant", "content": "Nice to meet you, Yash!"},
        ]
        state = _blank_state(
            user_request="What is my name?",
            messages=messages,
        )
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
            result = answer_generation_node(state)

            # Check that the prompt includes conversation history
            sent_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertIn("CONVERSATION HISTORY", sent_prompt.user)
            self.assertIn("My name is Yash", sent_prompt.user)
            self.assertIn("Nice to meet you, Yash!", sent_prompt.user)
            self.assertIn("What is my name?", sent_prompt.user)

    def test_empty_history_does_not_break_prompt(self):
        """Empty history should not break the prompt."""
        state = _blank_state(
            user_request="Hello",
            messages=[],
        )
        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock()
            mock_llm.name = "test"
            mock_llm.generate_structured.return_value = MagicMock(
                data={"answer": "Hi!", "cited_ids": [], "confidence": 0.9},
                model="test",
                input_tokens=10,
                output_tokens=10,
                total_tokens=20,
            )
            mock_get_llm.return_value = mock_llm
            result = answer_generation_node(state)

            sent_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            # Should NOT have CONVERSATION HISTORY section
            self.assertNotIn("CONVERSATION HISTORY", sent_prompt.user)
            self.assertIn("QUESTION: Hello", sent_prompt.user)


class TestBug3_DateTimeHandling(TestCase):
    """Test that date/time queries use runtime date/time."""

    def test_date_time_node_provides_formatted_date(self):
        """Date/time node should provide a formatted date string."""
        result = date_time_node(_blank_state(user_request="what is today's date?"))
        self.assertIn("current_date", result)
        # Should be formatted like "September 01, 2026"
        self.assertRegex(result["current_date"], r"[A-Z][a-z]+ \d{2}, \d{4}")

    def test_date_time_in_prompt(self):
        """Date/time should be injected into the prompt."""
        state = _blank_state(
            user_request="what is today's date?",
            current_date="September 01, 2026",
        )
        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock()
            mock_llm.name = "test"
            mock_llm.generate_structured.return_value = MagicMock(
                data={"answer": "Today is September 1, 2026.", "cited_ids": [], "confidence": 0.9},
                model="test",
                input_tokens=10,
                output_tokens=10,
                total_tokens=20,
            )
            mock_get_llm.return_value = mock_llm
            result = answer_generation_node(state)

            sent_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            self.assertIn("CURRENT DATE/TIME: September 01, 2026", sent_prompt.user)

    def test_various_date_patterns_route_correctly(self):
        """Various date/time patterns should all route to date_time."""
        date_queries = [
            "what is today's date?",
            "what's today's date?",
            "what date is it?",
            "what's the date?",
            "today's date",
            "what time is it?",
            "what's the time?",
            "what day is it?",
        ]
        for query in date_queries:
            result = route_query_node(_blank_state(user_request=query))
            self.assertEqual(result["route"], "date_time", f"Query '{query}' should route to date_time")


class TestRoutingExplicitness(TestCase):
    """Test that routing is explicit and covers all categories."""

    def test_conversational_patterns(self):
        """Conversational patterns should route correctly."""
        conversational_queries = [
            "hi", "hello", "hey", "thanks", "thank you",
            "my name is yash", "i am john", "i'm alice",
            "what is my name?", "do you remember my name?",
            "what did i just tell you?", "who am i?",
        ]
        for query in conversational_queries:
            result = route_query_node(_blank_state(user_request=query))
            self.assertEqual(result["route"], "conversational", f"Query '{query}' should be conversational")

    def test_material_patterns(self):
        """Material patterns should route correctly."""
        material_queries = [
            "explain dynamic programming from my notes",
            "what does my textbook say about graphs?",
            "according to my notes, what is recursion?",
        ]
        for query in material_queries:
            result = route_query_node(_blank_state(user_request=query))
            self.assertEqual(result["route"], "material", f"Query '{query}' should be material")

    def test_general_knowledge_patterns(self):
        """General knowledge patterns should route correctly."""
        gk_queries = [
            "what is gradient descent?",
            "how does quicksort work?",
            "explain neural networks",
        ]
        for query in gk_queries:
            result = route_query_node(_blank_state(user_request=query))
            self.assertEqual(result["route"], "general_knowledge", f"Query '{query}' should be general_knowledge")


def _blank_state(**overrides):
    defaults = {
        "user_request": "",
        "profile_id": "p1",
        "subject_id": None,
        "session_id": "s1",
        "route": None,
        "messages": [],
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
        "current_date": None,
    }
    defaults.update(overrides)
    return ChatState(**defaults)
