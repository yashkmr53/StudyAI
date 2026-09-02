"""Agent Tool Unit Tests (Phase 1)."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

from django.test import TestCase
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from django.contrib.auth import get_user_model

from apps.agents.tools.retrieval import SearchNotesTool, SearchReferenceBooksTool
from apps.agents.tools.learning import GetMasteryTool
from apps.agents.tools.evidence import VerifyEvidenceTool
from apps.agents.tools.document import GetDocumentTool, GetSubjectContextTool
from apps.agents.tools.base import get_tool_registry

User = get_user_model()


@pytest.mark.django_db
class TestSearchNotesTool:
    @pytest.fixture
    def tool(self):
        return SearchNotesTool()

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email="test@example.com", password="testpass123")

    @pytest.fixture
    def profile(self, user):
        return Profile.objects.create(user=user, name="Test Profile")

    def test_search_notes_valid_input(self, tool, user, profile):
        with patch("apps.retrieval.retrieval.RetrievalService.search") as mock_search:
            mock_evidence = Mock()
            mock_evidence.chunk_id = str(uuid4())
            mock_evidence.document_id = str(uuid4())
            mock_evidence.source_type = "note"
            mock_evidence.page_start = 1
            mock_evidence.page_end = 2
            mock_evidence.content_snippet = "Test content"
            mock_evidence.dense_rank = 0.5
            mock_evidence.keyword_rank = 0.3
            mock_evidence.rrf_score = 0.4
            mock_search.return_value = [mock_evidence]

            result = tool.execute(
                tool.metadata.input_schema(query="test query", top_k=5),
                user=user,
                request_id="test-123"
            )

            assert result.success is True
            assert len(result.results) == 1
            assert result.results[0].chunk_id == mock_evidence.chunk_id
            assert result.query == "test query"

    def test_search_notes_empty_query(self, tool, user, profile):
        with pytest.raises(Exception):  # Pydantic validation error
            tool.execute(
                tool.metadata.input_schema(query="", top_k=5),
                user=user,
                request_id="test-123"
            )


@pytest.mark.django_db
class TestSearchReferenceBooksTool:
    @pytest.fixture
    def tool(self):
        return SearchReferenceBooksTool()

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email="test2@example.com", password="testpass123")

    @pytest.fixture
    def profile(self, user):
        return Profile.objects.create(user=user, name="Test Profile 2")

    def test_search_reference_books_filters_only_reference(self, tool, user, profile):
        with patch("apps.retrieval.retrieval.RetrievalService.search") as mock_search:
            mock_note = Mock()
            mock_note.chunk_id = str(uuid4())
            mock_note.document_id = str(uuid4())
            mock_note.source_type = "note"
            mock_note.page_start = 1
            mock_note.page_end = 2
            mock_note.content_snippet = "Note content"
            mock_note.dense_rank = 0.5
            mock_note.keyword_rank = 0.3
            mock_note.rrf_score = 0.4

            mock_ref = Mock()
            mock_ref.chunk_id = str(uuid4())
            mock_ref.document_id = str(uuid4())
            mock_ref.source_type = "reference"
            mock_ref.page_start = 10
            mock_ref.page_end = 11
            mock_ref.content_snippet = "Reference content"
            mock_ref.dense_rank = 0.6
            mock_ref.keyword_rank = 0.4
            mock_ref.rrf_score = 0.5

            mock_search.return_value = [mock_note, mock_ref]

            result = tool.execute(
                tool.metadata.input_schema(query="test query", top_k=5),
                user=user,
                request_id="test-123"
            )

            assert result.success is True
            assert len(result.results) == 1
            assert result.results[0].source_type == "reference"


@pytest.mark.django_db
class TestGetMasteryTool:
    @pytest.fixture
    def tool(self):
        return GetMasteryTool()

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email="test3@example.com", password="testpass123")

    @pytest.fixture
    def profile(self, user):
        return Profile.objects.create(user=user, name="Test Profile 3")

    def test_get_mastery_returns_structured_data(self, tool, user, profile):
        with patch("apps.revision.services.RevisionPlanningService.overview") as mock_overview:
            mock_overview.return_value = {
                "tags": [
                    {
                        "tag_id": str(uuid4()),
                        "stable_key": "neural_networks",
                        "display_name": "Neural Networks",
                        "status": "weak",
                        "mastery": 0.3,
                        "attempt_count": 5,
                        "last_assessed_at": None,
                    }
                ],
                "assessed_count": 1,
                "not_assessed_count": 0,
            }

            result = tool.execute(
                tool.metadata.input_schema(subject_id=None),
                user=user,
                request_id="test-123"
            )

            assert result.success is True
            assert len(result.tags) == 1
            assert result.tags[0].stable_key == "neural_networks"
            assert result.tags[0].mastery == 0.3
            assert result.assessed_count == 1


@pytest.mark.django_db
class TestVerifyEvidenceTool:
    @pytest.fixture
    def tool(self):
        return VerifyEvidenceTool()

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email="test4@example.com", password="testpass123")

    @pytest.fixture
    def profile(self, user):
        return Profile.objects.create(user=user, name="Test Profile 4")

    def test_verify_evidence_supported(self, tool, user, profile):
        with patch("apps.ai_classroom.services.EvidenceVerifier.verify") as mock_verify:
            mock_verify.return_value = ("supported", 0.85)

            result = tool.execute(
                tool.metadata.input_schema(
                    content="Neural networks use backpropagation",
                    source_refs=[{"chunk_id": str(uuid4()), "document_id": str(uuid4())}]
                ),
                user=user,
                request_id="test-123"
            )

            assert result.success is True
            assert result.status == "supported"
            assert result.score == 0.85

    def test_verify_evidence_unsupported(self, tool, user, profile):
        with patch("apps.ai_classroom.services.EvidenceVerifier.verify") as mock_verify:
            mock_verify.return_value = ("unsupported", 0.1)

            result = tool.execute(
                tool.metadata.input_schema(
                    content="Unrelated content",
                    source_refs=[{"chunk_id": str(uuid4())}]
                ),
                user=user,
                request_id="test-123"
            )

            assert result.success is True
            assert result.status == "unsupported"
            assert result.score == 0.1


@pytest.mark.django_db
class TestToolRegistry:
    def test_registry_contains_expected_tools(self):
        registry = get_tool_registry()
        tools = registry.list_tools()
        tool_names = [t.metadata.name for t in tools]

        expected = [
            "search_notes",
            "search_reference_books",
            "get_mastery",
            "verify_evidence",
            "get_document",
            "get_subject_context",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    def test_tool_schemas_are_valid(self):
        registry = get_tool_registry()
        for tool in registry.list_tools():
            # Input schema should be instantiable with required fields
            if tool.metadata.name == "search_notes":
                input_instance = tool.metadata.input_schema(query="test", top_k=5)
            elif tool.metadata.name == "search_reference_books":
                input_instance = tool.metadata.input_schema(query="test", top_k=5)
            elif tool.metadata.name == "get_mastery":
                input_instance = tool.metadata.input_schema()
            elif tool.metadata.name == "get_revision_plan":
                input_instance = tool.metadata.input_schema(subject_id=None, target_date="2026-12-31")
            elif tool.metadata.name == "get_previous_questions":
                input_instance = tool.metadata.input_schema()
            elif tool.metadata.name == "generate_questions":
                input_instance = tool.metadata.input_schema(document_id=str(uuid4()), count=5)
            elif tool.metadata.name == "create_test":
                input_instance = tool.metadata.input_schema()
            elif tool.metadata.name == "verify_evidence":
                input_instance = tool.metadata.input_schema(content="test", source_refs=[{"chunk_id": str(uuid4())}])
            elif tool.metadata.name == "verify_citations":
                input_instance = tool.metadata.input_schema(citations=[])
            elif tool.metadata.name == "get_document":
                input_instance = tool.metadata.input_schema(document_id=str(uuid4()))
            elif tool.metadata.name == "get_subject_context":
                input_instance = tool.metadata.input_schema(subject_id=str(uuid4()))
            elif tool.metadata.name == "search_web":
                input_instance = tool.metadata.input_schema(query="test", max_results=5)
            else:
                input_instance = tool.metadata.input_schema()
            assert input_instance is not None

            # Output schema should be instantiable with required fields
            if tool.metadata.name == "search_notes":
                output_instance = tool.metadata.output_schema(results=[], query="test")
            elif tool.metadata.name == "search_reference_books":
                output_instance = tool.metadata.output_schema(results=[], query="test")
            elif tool.metadata.name == "get_mastery":
                output_instance = tool.metadata.output_schema(tags=[], assessed_count=0, not_assessed_count=0)
            elif tool.metadata.name == "get_revision_plan":
                output_instance = tool.metadata.output_schema(target_date="2026-12-31", days_left=30, priorities=[], schedule=[])
            elif tool.metadata.name == "get_previous_questions":
                output_instance = tool.metadata.output_schema(questions=[])
            elif tool.metadata.name == "generate_questions":
                output_instance = tool.metadata.output_schema(questions=[], test_id=None)
            elif tool.metadata.name == "create_test":
                output_instance = tool.metadata.output_schema(test_id=str(uuid4()), questions=[])
            elif tool.metadata.name == "mastery_aware_test_generation":
                output_instance = tool.metadata.output_schema(
                    test_id=str(uuid4()),
                    questions=[],
                    weak_topics_used=[],
                    total_questions_generated=0
                )
            elif tool.metadata.name == "verify_evidence":
                output_instance = tool.metadata.output_schema(status="supported", score=0.5, verifier_version="v1")
            elif tool.metadata.name == "verify_citations":
                output_instance = tool.metadata.output_schema(verifications=[], verifier_version="v1")
            elif tool.metadata.name == "get_document":
                from apps.agents.tools.document import DocumentInfo
                output_instance = tool.metadata.output_schema(document=DocumentInfo(document_id=str(uuid4()), title="test", source_type="note", page_count=1, status="ready"))
            elif tool.metadata.name == "get_subject_context":
                from apps.agents.tools.document import SubjectContext
                output_instance = tool.metadata.output_schema(context=SubjectContext(subject_id=str(uuid4()), subject_name="test", document_count=0, documents=[], tags=[]))
            else:
                output_instance = tool.metadata.output_schema()
            assert output_instance is not None