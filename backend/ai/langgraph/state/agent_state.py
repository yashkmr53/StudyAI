"""Typed state for the Agentic LangGraph workflow."""
from typing import TypedDict, Optional, Any, List, Dict

from ai.langgraph.state.base_state import BaseStudyAIState


class AgentState(BaseStudyAIState):
    user_request: str
    profile_id: str
    subject_id: Optional[str]
    session_id: str
    retrieved_evidence: List[Dict[str, Any]]
    selected_evidence: List[Dict[str, Any]]
    answer: str
    citations: List[Dict[str, Any]]
    verification_status: str
    verification_score: float
    tool_calls: List[Dict[str, Any]]
    iterations: int
    max_iterations: int
    max_tool_calls: int
    errors: List[str]
    execution_metadata: Dict[str, Any]
