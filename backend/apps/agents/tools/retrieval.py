"""Retrieval Tools (Phase 1).

Wraps existing RetrievalService.search for agent use.
"""
from typing import Optional
from pydantic import Field

from apps.agents.tools.base import ToolInput, ToolOutput, ToolMetadata, BaseTool
from apps.retrieval.retrieval import RetrievalService, Evidence


class EvidenceResult(ToolOutput):
    chunk_id: str
    document_id: str
    source_type: str
    page_start: int
    page_end: int
    snippet: str
    scores: dict[str, float | None]
    document_title: str | None = None
    subject_name: str | None = None


class SearchNotesInput(ToolInput):
    query: str = Field(..., min_length=1, max_length=4000, description="Search query")
    subject_id: Optional[str] = Field(None, description="Optional subject UUID to scope search")
    top_k: int = Field(8, ge=1, le=20, description="Number of results to return")


class SearchNotesOutput(ToolOutput):
    results: list[EvidenceResult]
    query: str


class SearchNotesTool(BaseTool):
    metadata = ToolMetadata(
        name="search_notes",
        description="Search the user's personal notes (documents, OCR transcriptions, enriched notes) using hybrid retrieval (dense + keyword + RRF). Returns top-k evidence chunks with citations.",
        input_schema=SearchNotesInput,
        output_schema=SearchNotesOutput,
        requires_auth=True,
        timeout_seconds=15,
        category="retrieval",
    )

    def _execute(self, input: SearchNotesInput, *, user, request_id: str) -> SearchNotesOutput:
        subject = None
        if input.subject_id:
            from apps.subjects.models import Subject
            try:
                subject = Subject.objects.get(pk=input.subject_id, profile__user=user)
            except (Subject.DoesNotExist, ValueError, TypeError):
                pass  # Subject not found or not owned — search without subject filter

        evidence = RetrievalService.search(
            user=user,
            query=input.query,
            subject=subject,
            top_k=input.top_k,
            include_reference=False,
        )

        results = [
            EvidenceResult(
                chunk_id=e.chunk_id,
                document_id=e.document_id,
                source_type=e.source_type,
                page_start=e.page_start,
                page_end=e.page_end,
                snippet=e.content_snippet,
                scores={
                    "dense": e.dense_rank,
                    "keyword": e.keyword_rank,
                    "rrf": e.rrf_score,
                },
                document_title=e.document_title,
                subject_name=e.subject_name,
            )
            for e in evidence
        ]

        return SearchNotesOutput(results=results, query=input.query)


class SearchReferenceBooksInput(ToolInput):
    query: str = Field(..., min_length=1, max_length=4000, description="Search query")
    subject_id: Optional[str] = Field(None, description="Optional subject UUID to scope search")
    top_k: int = Field(6, ge=1, le=20, description="Number of results to return")


class SearchReferenceBooksOutput(ToolOutput):
    results: list[EvidenceResult]
    query: str


class SearchReferenceBooksTool(BaseTool):
    metadata = ToolMetadata(
        name="search_reference_books",
        description="Search platform-curated reference books (textbooks, papers) using hybrid retrieval. Only returns chunks from books with READY status. Use for authoritative definitions, formulas, or concepts not in user notes.",
        input_schema=SearchReferenceBooksInput,
        output_schema=SearchReferenceBooksOutput,
        requires_auth=True,
        timeout_seconds=15,
        category="retrieval",
    )

    def _execute(self, input: SearchReferenceBooksInput, *, user, request_id: str) -> SearchReferenceBooksOutput:
        subject = None
        if input.subject_id:
            from apps.subjects.models import Subject
            try:
                subject = Subject.objects.get(pk=input.subject_id, profile__user=user)
            except (Subject.DoesNotExist, ValueError, TypeError):
                pass

        evidence = RetrievalService.search(
            user=user,
            query=input.query,
            subject=subject,
            top_k=input.top_k,
            include_reference=True,
        )

        # Filter to only reference chunks
        ref_evidence = [e for e in evidence if e.source_type == "reference"]

        results = [
            EvidenceResult(
                chunk_id=e.chunk_id,
                document_id=e.document_id,
                source_type=e.source_type,
                page_start=e.page_start,
                page_end=e.page_end,
                snippet=e.content_snippet,
                scores={
                    "dense": e.dense_rank,
                    "keyword": e.keyword_rank,
                    "rrf": e.rrf_score,
                },
                document_title=e.document_title,
                subject_name=e.subject_name,
            )
            for e in ref_evidence
        ]

        return SearchReferenceBooksOutput(results=results, query=input.query)


# Auto-register tools on module import
from apps.agents.tools import get_tool_registry
get_tool_registry().register(SearchNotesTool())
get_tool_registry().register(SearchReferenceBooksTool())