"""Question generation (architecture §17, §54).

Deterministic MCQs grounded in specific chunks. Questions bind to their
source revision/chunk and go stale when the source content is superseded;
historical attempts are never deleted.
"""
import logging

from django.conf import settings
from django.db import transaction

from apps.documents.models import Document
from apps.questions.models import Question, QuestionTagLink

logger = logging.getLogger(__name__)


class QuestionGenerationService:
    @staticmethod
    @transaction.atomic
    def generate_for_document(document: Document, max_questions: int = 3) -> list[Question]:
        """Generates up to max_questions MCQs from the document's active
        chunks. Idempotent per (revision, content_hash, question_key)."""
        from ai.langgraph.graphs.question_generation_graph import invoke_question_generation_graph
        from ai.langgraph.state.question_generation_state import QuestionGenerationState

        initial_state = QuestionGenerationState(
            document_id=str(document.pk),
            chunks=[],
            questions=[],
            validated_questions=[],
            verified_questions=[],
            persisted_questions=[],
            max_questions=max_questions,
            errors=[],
            execution_metadata={},
        )

        final_state = invoke_question_generation_graph(initial_state)
        persisted_ids = [q["id"] for q in final_state.get("persisted_questions", [])]

        created = list(Question.objects.filter(pk__in=persisted_ids))
        logger.info("Generated %s new question(s) for document %s", len(created), document.pk)
        return created
