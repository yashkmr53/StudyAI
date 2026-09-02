"""Tests for the SearchWebTool (Agent Mode)."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from apps.agents.tools.web import SearchWebTool, SearchWebInput, SearchWebOutput
from providers.web.mock import MockWebSearchProvider


class TestSearchWebTool(TestCase):
    def setUp(self):
        self.tool = SearchWebTool()

    def test_metadata(self):
        self.assertEqual(self.tool.metadata.name, "search_web")
        self.assertEqual(self.tool.metadata.category, "retrieval")
        self.assertFalse(self.tool.metadata.requires_auth)

    def test_search_web_returns_results(self):
        user = MagicMock()
        with patch("apps.agents.tools.web.get_web_search_provider") as mock_get:
            mock_get.return_value = MockWebSearchProvider()
            inp = SearchWebInput(query="gradient descent", max_results=3)
            result = self.tool.execute(inp, user=user, request_id="test-123")
            self.assertIsInstance(result, SearchWebOutput)
            self.assertTrue(result.success)
            self.assertEqual(result.result_count, 3)
            self.assertEqual(result.query, "gradient descent")
            self.assertEqual(len(result.results), 3)
            # Each result should have real metadata
            for r in result.results:
                self.assertTrue(r.url.startswith("http"))
                self.assertTrue(r.domain)
                self.assertTrue(r.title)

    def test_search_web_empty_query(self):
        user = MagicMock()
        with patch("apps.chat.langgraph_nodes.get_web_search_provider") as mock_get:
            mock_get.return_value = MockWebSearchProvider()
            # Empty query is rejected by Pydantic validation (min_length=1)
            with self.assertRaises(Exception):
                inp = SearchWebInput(query="", max_results=3)
                self.tool.execute(inp, user=user, request_id="test-123")


# Need MagicMock import
from unittest.mock import MagicMock
