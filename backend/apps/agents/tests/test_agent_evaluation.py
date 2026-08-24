"""Agent Evaluation Tests (Phase 2)."""

import pytest
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import TestCase
from apps.profiles.models import Profile
from apps.chat.models import ChatSession
from django.contrib.auth import get_user_model

from apps.evaluation.runner import AgentCase, run_agent_cases
from apps.agents.services.agent import StudyAIAgent

User = get_user_model()


@pytest.mark.django_db
class TestAgentEvaluation:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(email="eval@example.com", password="testpass123")

    @pytest.fixture
    def profile(self, user):
        return Profile.objects.create(user=user, name="Eval Profile")

    @pytest.fixture
    def session(self, profile):
        from apps.subjects.models import Subject
        subject = Subject.objects.create(profile=profile, name="Test Subject")
        return ChatSession.objects.create(profile=profile, subject=subject)

    def test_run_agent_cases_basic(self, user, profile, session):
        """Test basic agent evaluation runner."""
        cases = [
            AgentCase(
                user_request="What is machine learning?",
                expected_intent_category="question_answering",
                expected_tool_sequence=["search_notes"],
                expected_outcome="success",
            ),
        ]

        # Mock the agent to return predictable results
        with patch.object(StudyAIAgent, 'process_request') as mock_process:
            mock_result = Mock()
            mock_result.tool_calls = [
                Mock(tool="search_notes", success=True),
            ]
            mock_result.iterations = 1
            mock_result.outcome = "success"
            mock_result.verification_score = 0.8
            mock_process.return_value = mock_result

            metrics = run_agent_cases(cases, user, session)

            assert metrics["cases"] == 1
            assert metrics["tool_selection_accuracy"] >= 0.5  # Should get partial credit
            assert metrics["task_completion_rate"] == 1.0
            assert metrics["avg_tool_calls_per_task"] == 1.0

    def test_run_agent_cases_tool_sequence(self, user, profile, session):
        """Test agent evaluation with tool sequence checking."""
        cases = [
            AgentCase(
                user_request="Create a test on my weak topics",
                expected_intent_category="test_generation",
                expected_tool_sequence=["get_mastery", "search_notes", "generate_questions", "create_test"],
                expected_outcome="success",
            ),
        ]

        with patch.object(StudyAIAgent, 'process_request') as mock_process:
            mock_result = Mock()
            mock_result.tool_calls = [
                Mock(tool="get_mastery", success=True),
                Mock(tool="search_notes", success=True),
                Mock(tool="generate_questions", success=True),
                Mock(tool="create_test", success=True),
            ]
            mock_result.iterations = 4
            mock_result.outcome = "success"
            mock_result.verification_score = 0.85
            mock_process.return_value = mock_result

            metrics = run_agent_cases(cases, user, session)

            assert metrics["tool_sequence_accuracy"] == 1.0
            assert metrics["tool_selection_accuracy"] == 1.0
            assert metrics["avg_iterations_per_task"] == 4.0

    def test_run_agent_cases_partial_tool_match(self, user, profile, session):
        """Test agent evaluation with partial tool match."""
        cases = [
            AgentCase(
                user_request="Create a test",
                expected_intent_category="test_generation",
                expected_tool_sequence=["search_notes", "generate_questions"],
                expected_outcome="success",
            ),
        ]

        with patch.object(StudyAIAgent, 'process_request') as mock_process:
            mock_result = Mock()
            mock_result.tool_calls = [
                Mock(tool="get_mastery", success=True),
                Mock(tool="search_notes", success=True),
                Mock(tool="generate_questions", success=True),
            ]
            mock_result.iterations = 3
            mock_result.outcome = "success"
            mock_result.verification_score = 0.75
            mock_process.return_value = mock_result

            metrics = run_agent_cases(cases, user, session)

            # Should get partial credit for superset
            assert metrics["tool_selection_accuracy"] == 0.5
            # Sequence doesn't match exactly
            assert metrics["tool_sequence_accuracy"] == 0.0
            assert metrics["avg_tool_calls_per_task"] == 3.0