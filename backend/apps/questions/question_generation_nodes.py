"""Question generation graph nodes."""
import hashlib
import json
import logging
import time

from ai.langgraph.state.question_generation_state import QuestionGenerationState
from ai.tracing.config import log_llm_call
from ai.tracing.decorators import traced_node
from apps.documents.models import Document
from apps.questions.models import Question, QuestionTagLink
from providers.registry import get_llm_provider
from providers.base import Prompt

logger = logging.getLogger(__name__)


def _question_key(chunk_id: str, prompt_text: str) -> str:
    return hashlib.md5(f"{chunk_id}:{prompt_text}".encode()).hexdigest()[:32]


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

    return {
        "chunks": [
            {
                "chunk_id": str(c.pk),
                "content": c.content,
                "revision_id": str(c.revision_id) if c.revision_id else None,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]
    }


@traced_node("studyai.question_generation.generate", feature="question_generation")
def generate_questions_node(state: QuestionGenerationState, config=None) -> dict:
    llm = get_llm_provider()
    prompt_version = "v1"
    chunks = state.get("chunks", [])
    questions = []

    for i, chunk in enumerate(chunks):
        topic = chunk["content"].split()[0] if chunk["content"].split() else "this topic"
        evidence = {
            "chunk": {"chunk_id": chunk["chunk_id"], "content": chunk["content"], "topic": topic},
            "distractor_contents": [c["content"] for j, c in enumerate(chunks) if j != i],
        }

        prompt = Prompt(
            name="question_generation",
            version=prompt_version,
            user="EVIDENCE_JSON:" + json.dumps(evidence),
        )

        started = time.monotonic()
        result = llm.generate_structured(
            prompt=prompt,
            request_id=f"qgen:{chunk['chunk_id']}",
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

        question_data = {
            "chunk_id": chunk["chunk_id"],
            "revision_id": chunk.get("revision_id"),
            "prompt": result.data.get("prompt", ""),
            "options": result.data.get("options", []),
            "answer_index": result.data.get("answer_index", 0),
            "difficulty": result.data.get("difficulty", Question.Difficulty.MEDIUM),
            "question_key": _question_key(chunk["chunk_id"], result.data.get("prompt", "")),
            "content_hash": _content_hash(result.data.get("prompt", ""), result.data.get("options", [])),
        }
        questions.append(question_data)

    return {"questions": questions}


@traced_node("studyai.question_generation.validate", feature="question_generation")
def validate_questions_node(state: QuestionGenerationState, config=None) -> dict:
    questions = state.get("questions", [])
    validated = []

    for q in questions:
        options = q.get("options", [])
        answer_index = q.get("answer_index", 0)
        is_valid = (
            len(options) >= 2
            and 0 <= answer_index < len(options)
            and len(q.get("prompt", "")) > 10
        )
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

        chunk_id = q.get("chunk_id")
        prompt_text = q.get("prompt", "")
        status, score = EvidenceVerifier._classify(
            prompt_text, [q.get("prompt", "")]
        )
        verified.append({**q, "verification_status": status, "verification_score": score})

    return {"verified_questions": verified}


@traced_node("studyai.question_generation.persist", feature="question_generation")
def persist_questions_node(state: QuestionGenerationState, config=None) -> dict:
    document = Document.objects.get(pk=state["document_id"])
    verified = state.get("verified_questions", [])
    persisted = []
    model = getattr(__import__("django.conf", fromlist=["settings"]).settings, "ENRICHMENT_MODEL", "mock-gpt")
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
                "difficulty": q.get("difficulty", Question.Difficulty.MEDIUM),
                "prompt": q.get("prompt", ""),
                "options": q.get("options", []),
                "answer_index": q.get("answer_index", 0),
                "generation_model": model,
                "prompt_version": f"question_generation:{prompt_version}",
            },
        )
        if was_created and tag is not None:
            QuestionTagLink.objects.get_or_create(question=question, tag=tag)

        persisted.append({
            "id": str(question.pk),
            "prompt": question.prompt,
            "difficulty": question.difficulty,
            "verification_status": q.get("verification_status", "not_verified"),
        })

    logger.info("Persisted %s question(s) for document %s", len(persisted), document.pk)
    return {"persisted_questions": persisted}


def _primary_tag(document: Document):
    from apps.ai_classroom.models import DocumentTag
    link = DocumentTag.objects.filter(document=document).select_related("tag").first()
    return link.tag if link else None
