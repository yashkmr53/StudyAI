"""Pydantic schemas for structured LLM outputs in Chat workflows."""
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatAnswer(BaseModel):
    answer: str = Field(description="The answer to the user's question")
    cited_ids: List[str] = Field(
        description="List of citation_ids (e.g. SRC-001) cited in the answer"
    )
    confidence: float = Field(description="Confidence score between 0 and 1", ge=0.0, le=1.0)
    # Backward compat: some providers may still emit cited_chunk_ids
    cited_chunk_ids: List[str] = Field(
        default_factory=list,
        description="Deprecated: use cited_ids instead"
    )


class ChatAnswerRetry(ChatAnswer):
    reasoning: Optional[str] = Field(
        default=None,
        description="Reasoning for why the retry addresses verification issues"
    )
