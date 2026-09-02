"""Web Search Tool for Agent Mode.

Wraps the web search provider for agent use. Returns real URLs, titles,
and domains so the agent can cite web sources.
"""
from typing import Optional
from pydantic import Field

from apps.agents.tools.base import ToolInput, ToolOutput, ToolMetadata, BaseTool
from providers.registry import get_web_search_provider
from providers.web.base import WebSearchResult


class WebSearchResultItem(ToolOutput):
    title: str
    url: str
    snippet: str
    domain: str


class SearchWebInput(ToolInput):
    query: str = Field(..., min_length=1, max_length=4000, description="Search query")
    max_results: int = Field(5, ge=1, le=10, description="Number of results to return")


class SearchWebOutput(ToolOutput):
    results: list[WebSearchResultItem] = Field(default_factory=list)
    query: str = ""
    result_count: int = 0


class SearchWebTool(BaseTool):
    metadata = ToolMetadata(
        name="search_web",
        description=(
            "Search the web for current information, documentation, or general knowledge. "
            "Returns real URLs, titles, and snippets. Use for questions about current events, "
            "external documentation, or topics not in the user's notes."
        ),
        input_schema=SearchWebInput,
        output_schema=SearchWebOutput,
        requires_auth=False,
        timeout_seconds=20,
        category="retrieval",
    )

    def _execute(self, input: SearchWebInput, *, user, request_id: str) -> SearchWebOutput:
        provider = get_web_search_provider()
        results = provider.search(
            input.query,
            max_results=input.max_results,
            request_id=request_id,
        )

        output_results = [
            WebSearchResultItem(
                title=r.title,
                url=r.url,
                snippet=r.snippet,
                domain=r.domain,
            )
            for r in results
        ]

        return SearchWebOutput(
            results=output_results,
            query=input.query,
            result_count=len(output_results),
        )


# Auto-register tool on module import
from apps.agents.tools import get_tool_registry
get_tool_registry().register(SearchWebTool())
