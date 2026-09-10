"""Typed state for the Question Generation LangGraph workflow."""
from typing import TypedDict, Optional, Any, List, Dict

from ai.langgraph.state.base_state import BaseStudyAIState


class QuestionGenerationState(BaseStudyAIState):
    document_id: str
    chunks: List[Dict[str, Any]]
    questions: List[Dict[str, Any]]
    validated_questions: List[Dict[str, Any]]
    verified_questions: List[Dict[str, Any]]
    persisted_questions: List[Dict[str, Any]]
    max_questions: int
