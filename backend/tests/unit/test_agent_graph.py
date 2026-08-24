"""Phase 8 Agentic/MCP graph tests."""
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ai.langgraph.state.agent_state import AgentState
from ai.langgraph.graphs.agent_graph import (
    build_agent_graph,
    _branch_after_tool_execution,
)
from ai.langgraph.nodes.agent_nodes import (
    analyze_request_node,
    execute_tool_node,
    finalize_node,
    format_response_node,
    select_tool_node,
)


class MockProfile:
    def __init__(self, pk):
        self.pk = pk
        self.user = MagicMock()


class MockTool:
    def __init__(self, name, description):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.metadata.description = description
        self.metadata.category = "test"
        self.metadata.input_schema = MagicMock()
        self.metadata.output_schema = MagicMock()
        self.execute = MagicMock(return_value=MockToolResult(success=True, result={"results": []}))


class MockToolResult:
    def __init__(self, success=True, result=None, error=None):
        self.success = success
        self.model_dump = MagicMock(return_value=result or {})
        self.error = error
        self.latency_ms = 0


class MockLLMResult:
    def __init__(self, data, model):
        self.data = data
        self.model = model


class TestAgentGraphNodes(TestCase):
    def test_analyze_request_node(self):
        with patch("ai.langgraph.nodes.agent_nodes.Profile.objects.get") as mock_get, \
             patch("ai.langgraph.nodes.agent_nodes.get_tool_registry") as mock_registry:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_registry.return_value.list_tools.return_value = [
                MockTool("search_notes", "Search user notes"),
                MockTool("get_mastery", "Get mastery overview"),
            ]

            state = AgentState(
                user_request="test request",
                profile_id="profile-1",
                subject_id=None,
                session_id="session-1",
                retrieved_evidence=[],
                selected_evidence=[],
                answer="",
                citations=[],
                verification_status="not_verified",
                verification_score=0.0,
                tool_calls=[],
                iterations=0,
                max_iterations=5,
                max_tool_calls=10,
                errors=[],
                execution_metadata={},
            )

            result = analyze_request_node(state)
            self.assertIn("available_tools", result)
            self.assertEqual(len(result["available_tools"]), 2)

    def test_select_tool_node(self):
        with patch("ai.langgraph.nodes.agent_nodes.Profile.objects.get") as mock_get, \
             patch("providers.registry.get_llm_provider") as mock_llm, \
             patch("apps.agents.prompts.agent_prompts.AGENT_SYSTEM_PROMPT") as mock_prompt:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_prompt.format.return_value = "You are StudyAI Agent..."

            mock_llm_instance = MagicMock()
            mock_llm_instance.generate_structured.return_value = MockLLMResult(
                data={"tool": "search_notes", "arguments": {"query": "test"}, "reasoning": "test"},
                model="mock",
            )
            mock_llm.return_value = mock_llm_instance

            state = AgentState(
                user_request="test request",
                profile_id="profile-1",
                subject_id=None,
                session_id="session-1",
                retrieved_evidence=[],
                selected_evidence=[],
                answer="",
                citations=[],
                verification_status="not_verified",
                verification_score=0.0,
                tool_calls=[],
                iterations=0,
                max_iterations=5,
                max_tool_calls=10,
                errors=[],
                execution_metadata={},
                available_tools=[
                    {"name": "search_notes", "description": "Search user notes", "category": "retrieval"},
                ],
            )

            result = select_tool_node(state)
            self.assertIn("tool_call", result)
            self.assertIn("tool", result["tool_call"])
            self.assertIn("arguments", result["tool_call"])

            state = AgentState(
                user_request="test request",
                profile_id="profile-1",
                subject_id=None,
                session_id="session-1",
                retrieved_evidence=[],
                selected_evidence=[],
                answer="",
                citations=[],
                verification_status="not_verified",
                verification_score=0.0,
                tool_calls=[],
                iterations=0,
                max_iterations=5,
                max_tool_calls=10,
                errors=[],
                execution_metadata={},
                available_tools=[
                    {"name": "search_notes", "description": "Search user notes", "category": "retrieval"},
                ],
            )

            result = select_tool_node(state)
            self.assertIn("tool_call", result)
            self.assertIn("tool", result["tool_call"])
            self.assertIn("arguments", result["tool_call"])

    def test_execute_tool_node(self):
        with patch("ai.langgraph.nodes.agent_nodes.Profile.objects.get") as mock_get, \
             patch("ai.langgraph.nodes.agent_nodes.get_tool_registry") as mock_registry:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_tool = MockTool("search_notes", "Search user notes")
            mock_registry.return_value.get.return_value = mock_tool

            state = AgentState(
                user_request="test request",
                profile_id="profile-1",
                subject_id=None,
                session_id="session-1",
                retrieved_evidence=[],
                selected_evidence=[],
                answer="",
                citations=[],
                verification_status="not_verified",
                verification_score=0.0,
                tool_calls=[],
                iterations=0,
                max_iterations=5,
                max_tool_calls=10,
                errors=[],
                execution_metadata={},
                tool_call={"tool": "search_notes", "arguments": {"query": "test"}},
            )

            result = execute_tool_node(state)
            self.assertIn("last_tool_result", result)
            self.assertTrue(result["last_tool_result"]["success"])

    def test_format_response_node(self):
        state = AgentState(
            user_request="test request",
            profile_id="profile-1",
            subject_id=None,
            session_id="session-1",
            retrieved_evidence=[],
            selected_evidence=[],
            answer="",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            tool_calls=[],
            iterations=0,
            max_iterations=5,
            max_tool_calls=10,
            errors=[],
            execution_metadata={},
            last_tool_result={
                "success": True,
                "result": {"results": [{"snippet": "test snippet"}]},
            },
        )

        result = format_response_node(state)
        self.assertIn("answer", result)
        self.assertIn("test snippet", result["answer"])

    def test_finalize_node(self):
        state = AgentState(
            user_request="test request",
            profile_id="profile-1",
            subject_id=None,
            session_id="session-1",
            retrieved_evidence=[],
            selected_evidence=[],
            answer="test answer",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            tool_calls=[{"tool": "search_notes"}],
            iterations=1,
            max_iterations=5,
            max_tool_calls=10,
            errors=[],
            execution_metadata={},
        )

        result = finalize_node(state)
        self.assertEqual(result["answer"], "test answer")
        self.assertEqual(result["iterations"], 1)


class TestAgentGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_agent_graph()
        self.assertIsNotNone(graph)

    def test_branch_after_tool_execution_continue(self):
        state = {
            "iterations": 1,
            "max_iterations": 5,
            "tool_calls": [{"tool": "search_notes"}],
            "max_tool_calls": 10,
        }
        self.assertEqual(_branch_after_tool_execution(state), "select_tool")

    def test_branch_after_tool_execution_stop_iterations(self):
        state = {
            "iterations": 5,
            "max_iterations": 5,
            "tool_calls": [],
            "max_tool_calls": 10,
        }
        self.assertEqual(_branch_after_tool_execution(state), "format_response")

    def test_branch_after_tool_execution_stop_tool_calls(self):
        state = {
            "iterations": 1,
            "max_iterations": 5,
            "tool_calls": [{"tool": "search_notes"}] * 10,
            "max_tool_calls": 10,
        }
        self.assertEqual(_branch_after_tool_execution(state), "format_response")
