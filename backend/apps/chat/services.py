"""Chatbot service (architecture §16, §57).

User question → scoped hybrid retrieval → evidence-grounded answer via
the LLM provider (mock) → citation verification → persist messages.
Retrieval scoping guarantees the chatbot never sees another profile's
content.
"""
import json
import logging

from django.db import transaction

from apps.ai_classroom.services import EvidenceVerifier
from apps.chat.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

CHAT_PROMPT_VERSION = "chat:v1"


class ChatService:
    @staticmethod
    @transaction.atomic
    def ask(session: ChatSession, content: str) -> ChatMessage:
        from providers.llm.mock import MockLLMProvider
        from providers.base import Prompt
        from apps.retrieval.retrieval import RetrievalService

        content = (content or "").strip()
        if not content:
            from shared.exceptions import ValidationError

            raise ValidationError("Message content is required.")

        from apps.ai_classroom.budget import assert_within_budget

        assert_within_budget(session.profile_id)
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=content)

        evidence = RetrievalService.search(
            session.profile.user,
            content,
            subject=session.subject,
            top_k=4,
        )

        from providers.registry import get_llm_provider

        llm = get_llm_provider()
        payload = {
            "evidence": [
                {"chunk_id": e.chunk_id, "content": e.content_snippet} for e in evidence
            ]
        }
        result = llm.generate_structured(
            prompt=Prompt(name="chat", version="v1", user="EVIDENCE_JSON:" + json.dumps(payload)),
            request_id=f"chat:{session.pk}",
        )
        answer = result.data["answer"]
        cited_ids = result.data.get("cited_chunk_ids", [])

        by_id = {e.chunk_id: e for e in evidence}
        citations = []
        cited_contents = []
        for cid in cited_ids:
            ev = by_id.get(cid)
            if ev is None:
                continue
            cited_contents.append(ev.content_snippet)
            citations.append({
                "source_type": ev.source_type,
                "chunk_id": ev.chunk_id,
                "document_id": ev.document_id,
                "page_start": ev.page_start,
                "page_end": ev.page_end,
                "snippet": ev.content_snippet,
                "rrf_score": round(ev.rrf_score, 6),
            })

        status, score = EvidenceVerifier._classify(answer, cited_contents)

        from django.conf import settings

        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=answer,
            citations=citations + [{"verification_status": status, "verification_score": score,
                                     "verifier_version": EvidenceVerifier.VERSION}],
            model=getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
            prompt_version=CHAT_PROMPT_VERSION,
        )
        logger.info("Chat %s answered with %s citation(s) [%s]", session.pk, len(citations), status)
        return message
