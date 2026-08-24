"""Typed state for the Revision Planning LangGraph workflow."""
from typing import TypedDict, Optional, Any, List, Dict

from ai.langgraph.state.base_state import BaseStudyAIState


class RevisionPlanningState(BaseStudyAIState):
    profile_id: str
    subject_id: Optional[str]
    target_date: str
    days_left: int
    horizon: int
    weights: Dict[str, float]
    urgency: float
    candidates: List[Dict[str, Any]]
    priorities: List[Dict[str, Any]]
    schedule: List[Dict[str, Any]]
