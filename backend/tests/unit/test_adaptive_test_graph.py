"""Phase 6 Adaptive Test graph tests."""
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ai.langgraph.state.adaptive_test_state import AdaptiveTestState
from ai.langgraph.graphs.adaptive_test_graph import (
    build_adaptive_test_graph,
    _branch_after_identify_weak,
)
from apps.tests.adaptive_test_nodes import (
    create_test_node,
    format_output_node,
    generate_questions_node,
    get_mastery_node,
    identify_weak_topics_node,
    retrieve_notes_node,
    select_questions_node,
)


class MockProfile:
    def __init__(self, pk):
        self.pk = pk
        self.user = MagicMock()


class MockDocument:
    def __init__(self, pk, profile):
        self.pk = pk
        self.profile = profile


class MockQuestion:
    def __init__(self, pk, difficulty="medium"):
        self.pk = pk
        self.difficulty = difficulty
        self.prompt = "test"
        self.options = ["A", "B"]
        self.answer_index = 0
        self.source_chunk_id = "chunk-1"


class TestAdaptiveTestGraphNodes(TestCase):
    def test_get_mastery_node(self):
        with patch("apps.tests.adaptive_test_nodes.Profile.objects.get") as mock_get, \
             patch("apps.tests.adaptive_test_nodes.RevisionPlanningService.overview") as mock_overview:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_overview.return_value = {
                "tags": [
                    {"tag_id": "tag-1", "stable_key": "dijkstra", "display_name": "Dijkstra", "status": "weak", "mastery": 0.2, "attempt_count": 1, "last_assessed_at": "2024-01-01T00:00:00Z", "subject_id": None},
                ],
                "assessed_count": 1,
                "not_assessed_count": 0,
            }

            state = AdaptiveTestState(
                profile_id="profile-1",
                subject_id=None,
                num_questions=5,
                difficulty="hard",
                focus_weak_only=True,
                mastery_overview={},
                weak_tags=[],
                all_tags=[],
                retrieved_document_ids=[],
                generated_questions=[],
                selected_questions=[],
                test_id=None,
                errors=[],
                execution_metadata={},
            )

            result = get_mastery_node(state)
            self.assertIn("mastery_overview", result)
            self.assertEqual(result["mastery_overview"]["assessed_count"], 1)

    def test_identify_weak_topics_node(self):
        state = AdaptiveTestState(
            profile_id="profile-1",
            subject_id=None,
            num_questions=5,
            difficulty="hard",
            focus_weak_only=True,
            mastery_overview={
                "tags": [
                    {"tag_id": "tag-1", "stable_key": "dijkstra", "display_name": "Dijkstra", "status": "weak", "mastery": 0.2, "attempt_count": 1, "last_assessed_at": "2024-01-01T00:00:00Z", "subject_id": None},
                    {"tag_id": "tag-2", "stable_key": "bellman-ford", "display_name": "Bellman-Ford", "status": "strong", "mastery": 0.9, "attempt_count": 5, "last_assessed_at": "2024-01-01T00:00:00Z", "subject_id": None},
                ],
            },
            weak_tags=[],
            all_tags=[],
            retrieved_document_ids=[],
            generated_questions=[],
            selected_questions=[],
            test_id=None,
            errors=[],
            execution_metadata={},
        )

        result = identify_weak_topics_node(state)
        self.assertEqual(len(result["weak_tags"]), 1)
        self.assertEqual(result["weak_tags"][0]["stable_key"], "dijkstra")

    def test_identify_weak_topics_no_weak_raises(self):
        state = AdaptiveTestState(
            profile_id="profile-1",
            subject_id=None,
            num_questions=5,
            difficulty="hard",
            focus_weak_only=True,
            mastery_overview={
                "tags": [],
            },
            weak_tags=[],
            all_tags=[],
            retrieved_document_ids=[],
            generated_questions=[],
            selected_questions=[],
            test_id=None,
            errors=[],
            execution_metadata={},
        )

        with self.assertRaises(ValueError):
            identify_weak_topics_node(state)

    def test_retrieve_notes_node(self):
        with patch("apps.tests.adaptive_test_nodes.Profile.objects.get") as mock_get, \
             patch("apps.tests.adaptive_test_nodes.RetrievalService.search") as mock_search:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_evidence = [
                MagicMock(document_id="doc-1"),
                MagicMock(document_id="doc-2"),
            ]
            for e in mock_evidence:
                e.document_id = str(e.document_id)
            mock_search.return_value = mock_evidence

            state = AdaptiveTestState(
                profile_id="profile-1",
                subject_id=None,
                num_questions=5,
                difficulty="hard",
                focus_weak_only=True,
                mastery_overview={},
                weak_tags=[{"stable_key": "dijkstra"}],
                all_tags=[],
                retrieved_document_ids=[],
                generated_questions=[],
                selected_questions=[],
                test_id=None,
                errors=[],
                execution_metadata={},
            )

            result = retrieve_notes_node(state)
            self.assertIn("retrieved_document_ids", result)
            self.assertEqual(len(result["retrieved_document_ids"]), 2)

    def test_generate_questions_node(self):
        with patch("apps.tests.adaptive_test_nodes.Profile.objects.get") as mock_get, \
             patch("apps.tests.adaptive_test_nodes.Document.objects.get") as mock_doc_get, \
             patch("apps.tests.adaptive_test_nodes.QuestionGenerationService.generate_for_document") as mock_gen:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_document = MockDocument("doc-1", mock_profile)
            mock_doc_get.return_value = mock_document
            mock_gen.return_value = [
                MockQuestion("q-1", "hard"),
                MockQuestion("q-2", "medium"),
            ]

            state = AdaptiveTestState(
                profile_id="profile-1",
                subject_id=None,
                num_questions=5,
                difficulty="hard",
                focus_weak_only=True,
                mastery_overview={},
                weak_tags=[],
                all_tags=[],
                retrieved_document_ids=["doc-1"],
                generated_questions=[],
                selected_questions=[],
                test_id=None,
                errors=[],
                execution_metadata={},
            )

            result = generate_questions_node(state)
            self.assertEqual(len(result["generated_questions"]), 2)

    def test_select_questions_node(self):
        state = AdaptiveTestState(
            profile_id="profile-1",
            subject_id=None,
            num_questions=2,
            difficulty="hard",
            focus_weak_only=True,
            mastery_overview={},
            weak_tags=[],
            all_tags=[],
            retrieved_document_ids=[],
            generated_questions=[
                {"id": "q-1", "difficulty": "hard"},
                {"id": "q-2", "difficulty": "medium"},
                {"id": "q-3", "difficulty": "hard"},
            ],
            selected_questions=[],
            test_id=None,
            errors=[],
            execution_metadata={},
        )

        result = select_questions_node(state)
        self.assertEqual(len(result["selected_questions"]), 2)
        self.assertEqual(result["selected_questions"][0]["id"], "q-1")

    def test_select_questions_fallback_to_all(self):
        state = AdaptiveTestState(
            profile_id="profile-1",
            subject_id=None,
            num_questions=5,
            difficulty="easy",
            focus_weak_only=True,
            mastery_overview={},
            weak_tags=[],
            all_tags=[],
            retrieved_document_ids=[],
            generated_questions=[
                {"id": "q-1", "difficulty": "hard"},
                {"id": "q-2", "difficulty": "medium"},
            ],
            selected_questions=[],
            test_id=None,
            errors=[],
            execution_metadata={},
        )

        result = select_questions_node(state)
        self.assertEqual(len(result["selected_questions"]), 2)

    def test_create_test_node(self):
        with patch("apps.tests.adaptive_test_nodes.Profile.objects.get") as mock_get, \
             patch("apps.tests.adaptive_test_nodes.TestInstance.objects.create") as mock_create, \
             patch("apps.tests.adaptive_test_nodes.TestQuestion.objects.create"):
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_test = MagicMock()
            mock_test.pk = "test-1"
            mock_create.return_value = mock_test

            state = AdaptiveTestState(
                profile_id="profile-1",
                subject_id=None,
                num_questions=2,
                difficulty="hard",
                focus_weak_only=True,
                mastery_overview={},
                weak_tags=[],
                all_tags=[],
                retrieved_document_ids=[],
                generated_questions=[],
                selected_questions=[
                    {"id": "q-1", "prompt": "test"},
                    {"id": "q-2", "prompt": "test"},
                ],
                test_id=None,
                errors=[],
                execution_metadata={},
            )

            result = create_test_node(state)
            self.assertEqual(result["test_id"], "test-1")

    def test_format_output_node(self):
        state = AdaptiveTestState(
            profile_id="profile-1",
            subject_id=None,
            num_questions=2,
            difficulty="hard",
            focus_weak_only=True,
            mastery_overview={},
            weak_tags=[{"display_name": "Dijkstra"}],
            all_tags=[],
            retrieved_document_ids=[],
            generated_questions=[],
            selected_questions=[{"id": "q-1"}],
            test_id="test-1",
            errors=[],
            execution_metadata={},
        )

        result = format_output_node(state)
        self.assertEqual(result["test_id"], "test-1")
        self.assertEqual(result["total_questions_generated"], 1)
        self.assertEqual(result["weak_topics_used"], ["Dijkstra"])


class TestAdaptiveTestGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_adaptive_test_graph()
        self.assertIsNotNone(graph)

    def test_branch_after_identify_weak_with_tags(self):
        state = {"weak_tags": [{"tag_id": "tag-1"}]}
        self.assertEqual(_branch_after_identify_weak(state), "retrieve")
