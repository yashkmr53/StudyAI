"""Base tool wrapper preserving StudyAI auth/validation boundaries."""
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str = ""


class StudyAITool:
    name: str = ""
    description: str = ""
    input_schema: type[BaseModel] = BaseModel

    def run(self, arguments: dict, user, profile_id: str, subject_id: Optional[str] = None) -> ToolResult:
        raise NotImplementedError

    def validate_input(self, arguments: dict) -> ToolResult:
        try:
            self.input_schema(**arguments)
            return ToolResult(success=True)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
