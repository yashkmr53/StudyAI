"""Typed state for the Adaptive Test LangGraph workflow."""
from typing import TypedDict, Optional, Any, List, Dict

from ai.langgraph.state.base_state import BaseStudyAIState


class AdaptiveTestState(BaseStudyAIState):
    profile_id: str
    subject_id: Optional[str]
    num_questions: int
    difficulty: Optional[str]
    focus_weak_only: bool
    mastery_overview: Dict[str, Any]
    weak_tags: List[Dict[str, Any]]
    all_tags: List[Dict[str, Any]]
    retrieved_document_ids: List[str]
    generated_questions: List[Dict[str, Any]]
    selected_questions: List[Dict[str, Any]]
    test_id: Optional[str]
