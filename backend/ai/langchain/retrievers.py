"""StudyAI retriever wrapping existing RetrievalService for LangChain integration."""
from typing import Optional

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from apps.retrieval.retrieval import RetrievalService, Evidence


class StudyAIRetriever(BaseRetriever):
    user = None
    subject = None
    top_k: int = 8
    include_reference: bool = True

    def __init__(self, user, subject=None, top_k: int = 8, include_reference: bool = True):
        super().__init__()
        self.user = user
        self.subject = subject
        self.top_k = top_k
        self.include_reference = include_reference

    def _get_relevant_documents(self, query: str) -> list[Document]:
        evidence = RetrievalService.search(
            self.user,
            query,
            subject=self.subject,
            top_k=self.top_k,
            include_reference=self.include_reference,
        )
        return [
            Document(
                page_content=e.content_snippet,
                metadata={
                    "chunk_id": e.chunk_id,
                    "document_id": e.document_id,
                    "source_type": e.source_type,
                    "page_start": e.page_start,
                    "page_end": e.page_end,
                    "rrf_score": round(e.rrf_score, 6),
                },
            )
            for e in evidence
        ]

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        return self._get_relevant_documents(query)
