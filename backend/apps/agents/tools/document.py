"""Document/Context Tools (Phase 1).

Provides access to document metadata and subject context for the agent.
"""
from typing import Optional
from pydantic import Field

from apps.agents.tools.base import ToolInput, ToolOutput, ToolMetadata, BaseTool


class DocumentInfo(ToolOutput):
    document_id: str
    title: str
    source_type: str
    page_count: int
    status: str
    subject_id: Optional[str] = None
    subject_name: Optional[str] = None


class GetDocumentInput(ToolInput):
    document_id: str = Field(..., description="Document UUID")


class GetDocumentOutput(ToolOutput):
    document: DocumentInfo


class GetDocumentTool(BaseTool):
    metadata = ToolMetadata(
        name="get_document",
        description="Get metadata for a specific document owned by the user. Returns title, source type, page count, and subject info.",
        input_schema=GetDocumentInput,
        output_schema=GetDocumentOutput,
        requires_auth=True,
        timeout_seconds=5,
        category="document",
    )

    def _execute(self, input: GetDocumentInput, *, user, request_id: str) -> GetDocumentOutput:
        from apps.documents.models import Document
        from apps.profiles.models import Profile

        profile = Profile.objects.get(user=user)

        try:
            document = Document.objects.select_related("subject").get(pk=input.document_id, profile=profile)
        except (Document.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Document not found or access denied")

        doc_info = DocumentInfo(
            document_id=str(document.pk),
            title=document.title,
            source_type=document.source_type,
            page_count=document.pages.count(),
            status=document.status,
            subject_id=str(document.subject_id) if document.subject_id else None,
            subject_name=document.subject.name if document.subject else None,
        )

        return GetDocumentOutput(document=doc_info)


class SubjectContext(ToolOutput):
    subject_id: str
    subject_name: str
    document_count: int
    documents: list[DocumentInfo]
    tags: list[dict]


class GetSubjectContextInput(ToolInput):
    subject_id: str = Field(..., description="Subject UUID")


class GetSubjectContextOutput(ToolOutput):
    context: SubjectContext


class GetSubjectContextTool(BaseTool):
    metadata = ToolMetadata(
        name="get_subject_context",
        description="Get full context for a subject: all documents, tags, and document counts. Useful for understanding what material is available before searching.",
        input_schema=GetSubjectContextInput,
        output_schema=GetSubjectContextOutput,
        requires_auth=True,
        timeout_seconds=10,
        category="document",
    )

    def _execute(self, input: GetSubjectContextInput, *, user, request_id: str) -> GetSubjectContextOutput:
        from apps.subjects.models import Subject
        from apps.documents.models import Document
        from apps.ai_classroom.models import Tag, DocumentTag
        from apps.profiles.models import Profile

        profile = Profile.objects.get(user=user)

        try:
            subject = Subject.objects.get(pk=input.subject_id, profile=profile)
        except (Subject.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Subject not found or access denied")

        documents = Document.objects.filter(subject=subject, profile=profile).select_related("subject")
        doc_infos = [
            DocumentInfo(
                document_id=str(d.pk),
                title=d.title,
                source_type=d.source_type,
                page_count=d.pages.count(),
                status=d.status,
                subject_id=str(d.subject_id) if d.subject_id else None,
                subject_name=d.subject.name if d.subject else None,
            )
            for d in documents
        ]

        tags = Tag.objects.filter(subject=subject).values("id", "stable_key", "display_name")
        tag_list = [
            {"tag_id": str(t["id"]), "stable_key": t["stable_key"], "display_name": t["display_name"]}
            for t in tags
        ]

        context = SubjectContext(
            subject_id=str(subject.pk),
            subject_name=subject.name,
            document_count=len(doc_infos),
            documents=doc_infos,
            tags=tag_list,
        )

        return GetSubjectContextOutput(context=context)


# Auto-register tools on module import
from apps.agents.tools import get_tool_registry
get_tool_registry().register(GetDocumentTool())
get_tool_registry().register(GetSubjectContextTool())