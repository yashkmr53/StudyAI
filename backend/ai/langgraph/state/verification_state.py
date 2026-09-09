"""Typed state for the Verification LangGraph workflow."""
from typing import TypedDict, Optional, Any, List, Dict
from typing import Optional

from ai.langgraph.state.base_state import BaseStudyAIState


class VerificationState(BaseStudyAIState):
    content: str
    cited_contents: List[str]
    verification_status: str
    verification_score: float
