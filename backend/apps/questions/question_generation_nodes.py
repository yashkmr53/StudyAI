"""Question generation graph nodes (Phase 7).

Canonical generation powered by Qwen3.5:4B with:
- Multiple question formats (MCQs, flashcards, short-answer, explanations)
- Grounding in user notes + reference textbook chunks
- Mastery-aware difficulty adaptation (easy/medium/hard)
- Grounded evidence verification against actual source chunk text
"""
import hashlib
import json
import logging
import time
from typing import Any, Dict, List

from ai.langgraph.state.question_generation_state import QuestionGenerationState
from ai.schemas.questions import GeneratedQuestionItem
from ai.tracing.config import log_llm_call
from ai.tracing.decorators import traced_node
from apps.documents.models import Document
from apps.questions.models import Question, QuestionTagLink
from providers.base import Prompt
from providers.registry import get_llm_provider

logger = logging.getLogger(__name__)


def _question_key(chunk_id: str, prompt_text: str, q_type: str = "mcq", difficulty: str = "medium") -> str:
    return hashlib.md5(f"{chunk_id}:{q_type}:{difficulty}:{prompt_text}".encode()).hexdigest()[:32]


def _content_hash(prompt_text: str, options: list[str]) -> str:
    payload = json.dumps({"p": prompt_text, "o": options}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@traced_node("studyai.question_generation.retrieve", feature="question_generation")
def retrieve_chunks_node(state: QuestionGenerationState, config=None) -> dict:
    document = Document.objects.get(pk=state["document_id"])
    max_questions = state.get("max_questions", 3)

    chunks = list(
        document.chunks.filter(stale=False).order_by("chunk_index")[:max_questions]
    )
    user_chunks_data = [
        {
            "chunk_id": str(c.pk),
            "content": c.content,
            "revision_id": str(c.revision_id) if c.revision_id else None,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]

    reference_chunks_data = []
    if state.get("include_reference", True) and getattr(document, "subject_id", None):
        try:
            from apps.retrieval.models import NoteChunk

            ref_chunks = NoteChunk.objects.filter(
                subject_id=document.subject_id,
                reference_book__isnull=False,
                stale=False,
            )[:3]
            reference_chunks_data = [
                {
                    "chunk_id": str(r.pk),
                    "content": r.content,
                    "title": getattr(r.reference_book, "title", "Reference"),
                }
                for r in ref_chunks
            ]
        except Exception as exc:
            logger.debug("Could not retrieve reference chunks for subject: %s", exc)

    return {
        "chunks": user_chunks_data,
        "reference_chunks": reference_chunks_data,
    }


def _resolve_target_difficulty(state: QuestionGenerationState) -> str:
    if state.get("difficulty"):
        return state["difficulty"]
    mastery = state.get("mastery_level")
    if mastery in ("weak", "not_assessed"):
        return Question.Difficulty.EASY
    elif mastery == "fair":
        return Question.Difficulty.MEDIUM
    elif mastery == "strong":
        return Question.Difficulty.HARD
    return Question.Difficulty.MEDIUM


@traced_node("studyai.question_generation.generate", feature="question_generation")
def generate_questions_node(state: QuestionGenerationState, config=None) -> dict:
    llm = get_llm_provider()
    prompt_version = "v1"
    chunks = state.get("chunks", [])
    ref_chunks = state.get("reference_chunks", [])
    q_type = state.get("question_type") or Question.QuestionType.MCQ
    target_difficulty = _resolve_target_difficulty(state)
    questions = []

    for i, chunk in enumerate(chunks):
        topic = chunk["content"].split()[0] if chunk["content"].split() else "this topic"
        distractor_contents = [c["content"] for j, c in enumerate(chunks) if j != i]
        ref_contents = [r["content"] for r in ref_chunks]

        evidence = {
            "chunk": {"chunk_id": chunk["chunk_id"], "content": chunk["content"], "topic": topic},
            "distractor_contents": distractor_contents,
            "reference_contents": ref_contents,
            "question_type": q_type,
            "difficulty": target_difficulty,
        }

        system_content = (
            f"You are StudyAI's expert question generator. Generate a {target_difficulty} {q_type} question grounded strictly in the source chunk.\n"
            f"Requirements:\n"
            f"- Question Type: {q_type}\n"
            f"- Target Difficulty: {target_difficulty}\n"
            f"- For MCQ: prompt, exactly 4 distinct options (A, B, C, D), answer_index (0-3), and explanation.\n"
            f"- For Flashcard: prompt (front concept/question), options (empty or key points), answer_index (0), and explanation (back answer).\n"
            f"- For Short Answer: prompt (question), options (sample acceptable answers or empty), answer_index (0), and explanation (model answer and rubric).\n"
            f"- For Explanation: prompt ('Explain how/why...'), answer_index (0), and explanation (detailed multi-point rubric).\n"
        )

        prompt = Prompt(
            name="question_generation",
            version=prompt_version,
            system=system_content,
            user="EVIDENCE_JSON:" + json.dumps(evidence),
        )

        started = time.monotonic()
        result = llm.generate_structured(
            prompt=prompt,
            schema=GeneratedQuestionItem,
            request_id=f"qgen:{chunk['chunk_id']}",
            disable_fallback=True,
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        log_llm_call(
            model=result.model,
            provider=llm.name,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            success=True,
        )

        resp_data = result.data if isinstance(result.data, dict) else {}
        prompt_text = resp_data.get("prompt", "")
        options = resp_data.get("options", [])
        answer_index = resp_data.get("answer_index", 0)
        item_difficulty = target_difficulty or resp_data.get("difficulty", Question.Difficulty.MEDIUM)
        item_type = q_type or resp_data.get("question_type", Question.QuestionType.MCQ)
        explanation = resp_data.get("explanation", "")

        question_data = {
            "chunk_id": chunk["chunk_id"],
            "chunk_content": chunk["content"],
            "revision_id": chunk.get("revision_id"),
            "prompt": prompt_text,
            "options": options,
            "answer_index": answer_index,
            "difficulty": item_difficulty,
            "question_type": item_type,
            "explanation": explanation,
            "question_key": _question_key(chunk["chunk_id"], prompt_text, item_type, item_difficulty),
            "content_hash": _content_hash(prompt_text, options),
        }
        questions.append(question_data)

    return {"questions": questions}


@traced_node("studyai.question_generation.validate", feature="question_generation")
def validate_questions_node(state: QuestionGenerationState, config=None) -> dict:
    questions = state.get("questions", [])
    validated = []

    for q in questions:
        q_type = q.get("question_type", Question.QuestionType.MCQ)
        prompt = q.get("prompt", "")
        options = q.get("options", [])
        answer_index = q.get("answer_index", 0)
        explanation = q.get("explanation", "")

        if q_type == Question.QuestionType.MCQ:
            is_valid = (
                len(options) >= 2
                and 0 <= answer_index < len(options)
                and len(prompt) > 10
            )
        elif q_type == Question.QuestionType.FLASHCARD:
            is_valid = len(prompt) > 5 and (len(explanation) > 5 or len(options) > 0)
        elif q_type in (Question.QuestionType.SHORT_ANSWER, Question.QuestionType.EXPLANATION):
            is_valid = len(prompt) > 10 and len(explanation) > 5
        else:
            is_valid = len(prompt) > 5

        validated.append({**q, "is_valid": is_valid})

    return {"validated_questions": validated}


@traced_node("studyai.question_generation.verify", feature="question_generation")
def verify_evidence_node(state: QuestionGenerationState, config=None) -> dict:
    from apps.ai_classroom.services import EvidenceVerifier

    validated = state.get("validated_questions", [])
    verified = []

    for q in validated:
        if not q.get("is_valid", False):
            verified.append({**q, "verification_status": "skipped"})
            continue

        prompt_text = q.get("prompt", "")
        # Compare prompt against actual source chunk content (grounding check)
        source_content = q.get("chunk_content") or prompt_text
        status, score = EvidenceVerifier._classify(
            prompt_text, [source_content]
        )
        verified.append({**q, "verification_status": status, "verification_score": score})

    return {"verified_questions": verified}


@traced_node("studyai.question_generation.persist", feature="question_generation")
def persist_questions_node(state: QuestionGenerationState, config=None) -> dict:
    document = Document.objects.get(pk=state["document_id"])
    verified = state.get("verified_questions", [])
    persisted = []
    model = getattr(__import__("django.conf", fromlist=["settings"]).settings, "LLM_MODEL", "qwen3.5:4b")
    prompt_version = "v1"

    tag = _primary_tag(document)

    for q in verified:
        if not q.get("is_valid", False):
            continue

        question, was_created = Question.objects.get_or_create(
            source_revision_id=q["revision_id"],
            content_hash=q["content_hash"],
            question_key=q["question_key"],
            defaults={
                "document": document,
                "source_chunk_id": q["chunk_id"],
                "question_type": q.get("question_type", Question.QuestionType.MCQ),
                "difficulty": q.get("difficulty", Question.Difficulty.MEDIUM),
                "prompt": q.get("prompt", ""),
                "options": q.get("options", []),
                "answer_index": q.get("answer_index", 0),
                "explanation": q.get("explanation", ""),
                "generation_model": model,
                "prompt_version": f"question_generation:{prompt_version}",
            },
        )
        if not was_created:
            updated_fields = []
            if q.get("question_type") and question.question_type != q["question_type"]:
                question.question_type = q["question_type"]
                updated_fields.append("question_type")
            if q.get("explanation") and not question.explanation:
                question.explanation = q["explanation"]
                updated_fields.append("explanation")
            if updated_fields:
                question.save(update_fields=updated_fields)

        if was_created and tag is not None:
            QuestionTagLink.objects.get_or_create(question=question, tag=tag)

        persisted.append({
            "id": str(question.pk),
            "prompt": question.prompt,
            "difficulty": question.difficulty,
            "question_type": getattr(question, "question_type", "mcq"),
            "explanation": getattr(question, "explanation", ""),
            "verification_status": q.get("verification_status", "not_verified"),
        })

    logger.info("Persisted %s question(s) for document %s", len(persisted), document.pk)
    return {"persisted_questions": persisted}


def _primary_tag(document: Document):
    from apps.ai_classroom.models import DocumentTag

    link = DocumentTag.objects.filter(document=document).select_related("tag").first()
    return link.tag if link else None
