"""Evidence Verification Tools (Phase 1).

Wraps existing EvidenceVerifier for agent use.
"""
from typing import Optional
from pydantic import Field

from apps.agents.tools.base import ToolInput, ToolOutput, ToolMetadata, BaseTool


class SourceRef(ToolOutput):
    chunk_id: str
    document_id: Optional[str] = None
    page_number: Optional[int] = None
    revision_id: Optional[str] = None
    retrieval_score: Optional[float] = None


class VerifyEvidenceInput(ToolInput):
    content: str = Field(..., min_length=1, max_length=10000, description="Content to verify")
    source_refs: list[SourceRef] = Field(..., min_length=1, description="List of source references to verify against")


class VerifyEvidenceOutput(ToolOutput):
    status: str = Field(..., description="Verification status: supported, partially_supported, unsupported, not_verified")
    score: Optional[float] = Field(None, description="Lexical support score (0-1)")
    verifier_version: str


class VerifyEvidenceTool(BaseTool):
    metadata = ToolMetadata(
        name="verify_evidence",
        description="Verify whether a piece of content is supported by the cited source chunks. Uses lexical overlap scoring with configurable thresholds. Returns verification status and confidence score.",
        input_schema=VerifyEvidenceInput,
        output_schema=VerifyEvidenceOutput,
        requires_auth=True,
        timeout_seconds=10,
        category="evidence",
    )

    def _execute(self, input: VerifyEvidenceInput, *, user, request_id: str) -> VerifyEvidenceOutput:
        from apps.ai_classroom.services import EvidenceVerifier

        refs = [
            {
                "chunk_id": ref.chunk_id,
                "document_id": ref.document_id,
                "page_number": ref.page_number,
                "revision_id": ref.revision_id,
                "retrieval_score": ref.retrieval_score,
            }
            for ref in input.source_refs
        ]

        status, score = EvidenceVerifier.verify(input.content, refs)

        return VerifyEvidenceOutput(
            status=status,
            score=score,
            verifier_version=EvidenceVerifier.VERSION,
        )


class VerifyCitationsInput(ToolInput):
    citations: list[dict] = Field(..., description="List of {content: str, source_refs: SourceRef[]}")


class CitationVerification(ToolOutput):
    content: str
    status: str
    score: Optional[float] = None


class VerifyCitationsOutput(ToolOutput):
    verifications: list[CitationVerification]
    verifier_version: str


class VerifyCitationsTool(BaseTool):
    metadata = ToolMetadata(
        name="verify_citations",
        description="Batch verify multiple citation blocks. Useful for verifying all citations in a generated answer at once.",
        input_schema=VerifyCitationsInput,
        output_schema=VerifyCitationsOutput,
        requires_auth=True,
        timeout_seconds=20,
        category="evidence",
    )

    def _execute(self, input: VerifyCitationsInput, *, user, request_id: str) -> VerifyCitationsOutput:
        from apps.ai_classroom.services import EvidenceVerifier

        verifications = []
        for citation in input.citations:
            content = citation.get("content", "")
            refs = citation.get("source_refs", [])

            if not content or not refs:
                verifications.append(CitationVerification(
                    content=content,
                    status="not_verified",
                    score=None,
                ))
                continue

            status, score = EvidenceVerifier.verify(content, refs)
            verifications.append(CitationVerification(
                content=content,
                status=status,
                score=score,
            ))

        return VerifyCitationsOutput(
            verifications=verifications,
            verifier_version=EvidenceVerifier.VERSION,
        )


# Auto-register tools on module import
from apps.agents.tools import get_tool_registry
get_tool_registry().register(VerifyEvidenceTool())
get_tool_registry().register(VerifyCitationsTool())