"""Question generation (architecture §17, §54).

Deterministic MCQs grounded in specific chunks. Questions bind to their
source revision/chunk and go stale when the source content is superseded;
historical attempts are never deleted.
"""
import hashlib
import json
import logging

from django.conf import settings
from django.db import transaction

from apps.ai_classroom.models import DocumentTag, Tag
from apps.documents.models import Document
from apps.questions.models import Question, QuestionTagLink
from providers.base import Prompt

logger = logging.getLogger(__name__)


def _question_key(chunk_id: str, prompt_text: str) -> str:
    return hashlib.md5(f"{chunk_id}:{prompt_text}".encode()).hexdigest()[:32]


def _content_hash(prompt_text: str, options: list[str]) -> str:
    payload = json.dumps({"p": prompt_text, "o": options}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _primary_tag(document: Document) -> Tag | None:
    link = DocumentTag.objects.filter(document=document).select_related("tag").first()
    return link.tag if link else None


class QuestionGenerationService:
    @staticmethod
    @transaction.atomic
    def generate_for_document(document: Document, max_questions: int = 3) -> list[Question]:
        """Generates up to max_questions MCQs from the document's active
        chunks. Idempotent per (revision, content_hash, question_key)."""
        from providers.llm.mock import MockLLMProvider

        chunks = list(
            document.chunks.filter(stale=False).order_by("chunk_index")[:max_questions]
        )
        if not chunks:
            return []

        from providers.registry import get_llm_provider

        llm = get_llm_provider()
        prompt_version = getattr(settings, "QUESTION_PROMPT_VERSION", "v1")
        model = getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")
        created: list[Question] = []
        contents = [c.content for c in chunks]

        for i, chunk in enumerate(chunks):
            topic = chunk.content.split()[0] if chunk.content.split() else "this topic"
            evidence = {
                "chunk": {"chunk_id": str(chunk.pk), "content": chunk.content, "topic": topic},
                "distractor_contents": [c for j, c in enumerate(contents) if j != i],
            }
            result = llm.generate_structured(
                prompt=Prompt(
                    name="question_generation",
                    version=prompt_version,
                    user="EVIDENCE_JSON:" + json.dumps(evidence),
                ),
                request_id=f"qgen:{chunk.pk}",
            )

            question_key = _question_key(str(chunk.pk), result.data["prompt"])
            hash_value = _content_hash(result.data["prompt"], result.data["options"])
            question, was_created = Question.objects.get_or_create(
                source_revision_id=chunk.revision_id,
                content_hash=hash_value,
                question_key=question_key,
                defaults={
                    "document": document,
                    "source_chunk_id": chunk.pk,
                    "difficulty": result.data.get("difficulty", Question.Difficulty.MEDIUM),
                    "prompt": result.data["prompt"],
                    "options": result.data["options"],
                    "answer_index": result.data["answer_index"],
                    "generation_model": model,
                    "prompt_version": f"question_generation:{prompt_version}",
                },
            )
            if was_created:
                created.append(question)
                tag = _primary_tag(document)
                if tag is not None:
                    QuestionTagLink.objects.create(question=question, tag=tag)

        logger.info("Generated %s new question(s) for document %s", len(created), document.pk)
        return created
