"""Typed state for the Question Generation LangGraph workflow (Phase 7)."""
from typing import Any, Dict, List, Optional

from ai.langgraph.state.base_state import BaseStudyAIState


class QuestionGenerationState(BaseStudyAIState, total=False):
    document_id: str
    chunks: List[Dict[str, Any]]
    reference_chunks: List[Dict[str, Any]]
    questions: List[Dict[str, Any]]
    validated_questions: List[Dict[str, Any]]
    verified_questions: List[Dict[str, Any]]
    persisted_questions: List[Dict[str, Any]]
    max_questions: int
    question_type: str  # "mcq", "flashcard", "short_answer", "explanation"
    difficulty: Optional[str]  # "easy", "medium", "hard"
    mastery_level: Optional[str]  # "weak", "fair", "strong", "not_assessed"
    include_reference: bool
