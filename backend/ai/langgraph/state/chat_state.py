"""Typed state for the Ask StudyAI (Chat) LangGraph workflow."""
from typing import TypedDict, Optional, Any

from ai.langgraph.state.base_state import BaseStudyAIState


class ChatState(BaseStudyAIState):
    user_request: str
    profile_id: str
    subject_id: Optional[str]
    session_id: str
    route: Optional[str]  # "conversational" | "date_time" | "material" | "general_knowledge"
    messages: list[dict[str, Any]]  # conversation history [{role, content}, ...]
    retrieved_evidence: list[dict[str, Any]]  # uploaded study material evidence
    web_evidence: list[dict[str, Any]]  # web search evidence
    selected_evidence: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    verification_status: str
    verification_score: float
    retry_count: int
    cited_contents: list[str]
    current_date: Optional[str]  # runtime date/time for date/time queries
