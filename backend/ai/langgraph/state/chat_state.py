"""Typed state for the Ask StudyAI (Chat) LangGraph workflow."""
from typing import TypedDict, Optional, Any

from ai.langgraph.state.base_state import BaseStudyAIState


class ChatState(BaseStudyAIState):
    user_request: str
    profile_id: str
    subject_id: Optional[str]
    session_id: str
    retrieved_evidence: list[dict[str, Any]]
    selected_evidence: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    verification_status: str
    verification_score: float
    retry_count: int
