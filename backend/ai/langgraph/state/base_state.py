"""Base state for StudyAI LangGraph workflows."""
from typing import TypedDict, Optional, Any


class BaseStudyAIState(TypedDict, total=False):
    errors: list[str]
    execution_metadata: dict[str, Any]
