"""Pydantic schemas for Question Generation workflows (Phase 7)."""
from typing import List, Optional
from pydantic import BaseModel, Field


class GeneratedQuestionItem(BaseModel):
    prompt: str = Field(
        description="The question text, flashcard front, or prompt"
    )
    options: List[str] = Field(
        default_factory=list,
        description="For MCQ, exactly 4 distinct choices (A, B, C, D). For flashcard, short-answer, or explanation, sample answer points or empty.",
    )
    answer_index: int = Field(
        default=0,
        description="0-based index of the correct option for MCQ (0-3); 0 for flashcard/short_answer/explanation",
    )
    difficulty: str = Field(
        default="medium",
        description="Question difficulty: easy, medium, or hard",
    )
    question_type: str = Field(
        default="mcq",
        description="Format: mcq, flashcard, short_answer, or explanation",
    )
    explanation: str = Field(
        default="",
        description="Educational explanation of why the answer is correct, model answer, or rubric",
    )


class GeneratedQuestionsBatch(BaseModel):
    questions: List[GeneratedQuestionItem] = Field(
        default_factory=list,
        description="List of generated questions grounded in the source content",
    )
