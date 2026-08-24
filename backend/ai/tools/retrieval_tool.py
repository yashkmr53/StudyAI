"""Retrieval tool wrapping StudyAI's hybrid retrieval service."""
from typing import Optional

from ai.tools.base import StudyAITool, ToolResult
from apps.retrieval.retrieval import RetrievalService


class RetrievalInput(BaseModel):
    query: str = Field(description="The search query")
    top_k: int = Field(default=4, description="Number of results to return", ge=1, le=20)
    include_reference: bool = Field(default=True, description="Include reference book chunks")


class SearchNotesTool(StudyAITool):
    name = "search_notes"
    description = "Search the user's notes and documents using hybrid retrieval (dense + keyword + RRF)"
    input_schema = RetrievalInput

    def run(self, arguments: dict, user, profile_id: str, subject_id: Optional[str] = None) -> ToolResult:
        validation = self.validate_input(arguments)
        if not validation.success:
            return validation
        try:
            evidence = RetrievalService.search(
                user,
                arguments["query"],
                subject=subject_id,
                top_k=arguments.get("top_k", 4),
                include_reference=arguments.get("include_reference", True),
            )
            return ToolResult(success=True, data=[e.as_dict() for e in evidence])
        except Exception as e:
            return ToolResult(success=False, error=str(e))
