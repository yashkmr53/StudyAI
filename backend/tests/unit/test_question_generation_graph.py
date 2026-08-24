"""Phase 4 LangGraph question generation graph tests."""
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ai.langgraph.state.question_generation_state import QuestionGenerationState
from ai.langgraph.graphs.question_generation_graph import (
    build_question_generation_graph,
    _branch_after_validation,
)
from apps.questions.question_generation_nodes import (
    generate_questions_node,
    persist_questions_node,
    retrieve_chunks_node,
    validate_questions_node,
    verify_evidence_node,
)


class MockLLMProvider:
    model_name = "mock-gpt"
    name = "mock"

    def generate_structured(self, *, prompt=None, schema=None, request_id=None):
        return type("R", (), {
            "data": {
                "prompt": "What does Dijkstra compute?",
                "options": ["Shortest paths", "Longest paths", "Minimum spanning tree", "Topological sort"],
                "answer_index": 0,
                "difficulty": "medium",
            },
            "model": "mock-gpt",
            "prompt_name": getattr(prompt, 'name', 'question_generation'),
            "prompt_version": getattr(prompt, 'version', 'v1'),
            "input_tokens": 15,
            "output_tokens": 25,
            "total_tokens": 40,
        })()


class MockChunk:
    def __init__(self, pk, content, revision_id=None, chunk_index=0):
        self.pk = pk
        self.content = content
        self.revision_id = revision_id
        self.chunk_index = chunk_index


class MockQuestion:
    def __init__(self, pk, prompt, difficulty="medium"):
        self.pk = pk
        self.prompt = prompt
        self.difficulty = difficulty


class TestQuestionGenerationGraphNodes(TestCase):
    def test_retrieve_chunks_node(self):
        with patch("apps.questions.question_generation_nodes.Document.objects.get") as mock_get:
            mock_doc = MagicMock()
            mock_doc.chunks.filter.return_value.order_by.return_value.__getitem__.return_value = [
                MockChunk("chunk-1", "Dijkstra computes shortest paths", "rev-1", 0),
            ]
            mock_get.return_value = mock_doc

            state = QuestionGenerationState(
                document_id="doc-1",
                chunks=[],
                questions=[],
                validated_questions=[],
                verified_questions=[],
                persisted_questions=[],
                max_questions=3,
                errors=[],
                execution_metadata={},
            )

            result = retrieve_chunks_node(state)
            self.assertEqual(len(result["chunks"]), 1)
            self.assertEqual(result["chunks"][0]["chunk_id"], "chunk-1")

    def test_generate_questions_node(self):
        state = QuestionGenerationState(
            document_id="doc-1",
            chunks=[
                {"chunk_id": "chunk-1", "content": "Dijkstra computes shortest paths", "revision_id": "rev-1"}
            ],
            questions=[],
            validated_questions=[],
            verified_questions=[],
            persisted_questions=[],
            max_questions=3,
            errors=[],
            execution_metadata={},
        )

        with patch("apps.questions.question_generation_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.questions.question_generation_nodes.log_llm_call"):
            mock_get_llm.return_value = MockLLMProvider()
            result = generate_questions_node(state)

            self.assertEqual(len(result["questions"]), 1)
            self.assertIn("prompt", result["questions"][0])
            self.assertIn("options", result["questions"][0])

    def test_validate_questions_node_valid(self):
        state = QuestionGenerationState(
            document_id="doc-1",
            chunks=[],
            questions=[
                {
                    "chunk_id": "chunk-1",
                    "prompt": "What does Dijkstra compute?",
                    "options": ["A", "B", "C"],
                    "answer_index": 0,
                }
            ],
            validated_questions=[],
            verified_questions=[],
            persisted_questions=[],
            max_questions=3,
            errors=[],
            execution_metadata={},
        )

        result = validate_questions_node(state)
        self.assertEqual(len(result["validated_questions"]), 1)
        self.assertTrue(result["validated_questions"][0]["is_valid"])

    def test_validate_questions_node_invalid(self):
        state = QuestionGenerationState(
            document_id="doc-1",
            chunks=[],
            questions=[
                {
                    "chunk_id": "chunk-1",
                    "prompt": "Short",
                    "options": [],
                    "answer_index": 0,
                }
            ],
            validated_questions=[],
            verified_questions=[],
            persisted_questions=[],
            max_questions=3,
            errors=[],
            execution_metadata={},
        )

        result = validate_questions_node(state)
        self.assertEqual(len(result["validated_questions"]), 1)
        self.assertFalse(result["validated_questions"][0]["is_valid"])

    def test_verify_evidence_node(self):
        with patch("apps.ai_classroom.services.EvidenceVerifier") as mock_verifier:
            mock_verifier._classify.return_value = ("supported", 0.9)
            state = QuestionGenerationState(
                document_id="doc-1",
                chunks=[],
                questions=[],
                validated_questions=[
                    {
                        "chunk_id": "chunk-1",
                        "prompt": "What does Dijkstra compute?",
                        "is_valid": True,
                    }
                ],
                verified_questions=[],
                persisted_questions=[],
                max_questions=3,
                errors=[],
                execution_metadata={},
            )

            result = verify_evidence_node(state)
            self.assertEqual(result["verified_questions"][0]["verification_status"], "supported")

    def test_persist_questions_node(self):
        with patch("apps.questions.question_generation_nodes.Question.objects.get_or_create") as mock_get_or_create:
            with patch("apps.questions.question_generation_nodes.QuestionTagLink.objects.get_or_create"):
                with patch("apps.questions.question_generation_nodes._primary_tag") as mock_primary_tag:
                    mock_question = MagicMock()
                    mock_question.pk = "q-1"
                    mock_question.prompt = "test"
                    mock_question.difficulty = "medium"
                    mock_get_or_create.return_value = (mock_question, True)
                    mock_primary_tag.return_value = None

                    with patch("apps.questions.question_generation_nodes.Document.objects.get") as mock_doc_get:
                        mock_doc = MagicMock()
                        mock_doc_get.return_value = mock_doc

                        state = QuestionGenerationState(
                            document_id="doc-1",
                            chunks=[],
                            questions=[],
                            validated_questions=[],
                            verified_questions=[
                                {
                                    "chunk_id": "chunk-1",
                                    "revision_id": "rev-1",
                                    "prompt": "test question",
                                    "options": ["A", "B"],
                                    "answer_index": 0,
                                    "difficulty": "medium",
                                    "content_hash": "abc123",
                                    "question_key": "qk123",
                                    "is_valid": True,
                                }
                            ],
                            persisted_questions=[],
                            max_questions=3,
                            errors=[],
                            execution_metadata={},
                        )

                        result = persist_questions_node(state)
                        self.assertEqual(len(result["persisted_questions"]), 1)
                        self.assertEqual(result["persisted_questions"][0]["id"], "q-1")


class TestQuestionGenerationGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_question_generation_graph()
        self.assertIsNotNone(graph)

    def test_branch_after_validation_with_invalid(self):
        state = {"validated_questions": [{"is_valid": False}]}
        self.assertEqual(_branch_after_validation(state), "persist")

    def test_branch_after_validation_all_valid(self):
        state = {"validated_questions": [{"is_valid": True}]}
        self.assertEqual(_branch_after_validation(state), "verify")
