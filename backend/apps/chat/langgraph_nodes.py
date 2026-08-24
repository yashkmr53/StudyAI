"""Chat graph nodes for Ask StudyAI LangGraph workflow."""
import json
import logging
import time

from ai.langgraph.state.chat_state import ChatState
from ai.schemas.chat import ChatAnswer, ChatAnswerRetry
from ai.tracing.config import log_llm_call, log_retrieval
from ai.tracing.decorators import traced_node
from apps.ai_classroom.services import EvidenceVerifier
from apps.chat.models import ChatSession
from apps.retrieval.retrieval import RetrievalService
from providers.registry import get_llm_provider
from providers.base import Prompt
from django.conf import settings

logger = logging.getLogger(__name__)


@traced_node("studyai.chat.retrieve", feature="chat")
def retrieve_node(state: ChatState) -> dict:
    session_id = state.get("session_id")
    try:
        session = ChatSession.objects.select_related("profile__user", "subject").get(pk=session_id)
    except ChatSession.DoesNotExist:
        return {"errors": state.get("errors", []) + ["Session not found"]}

    query = state["user_request"]
    user = session.profile.user
    subject = session.subject

    start = time.monotonic()
    evidence = RetrievalService.search(
        user,
        query,
        subject=subject,
        top_k=getattr(settings, "CHAT_RETRIEVAL_TOP_K", 4),
        include_reference=True,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    log_retrieval(
        query=query,
        profile_id=str(session.profile_id),
        subject_id=str(subject.pk) if subject else None,
        k=4,
        results_count=len(evidence),
        latency_ms=latency_ms,
    )

    return {
        "retrieved_evidence": [e.as_dict() for e in evidence],
    }


@traced_node("studyai.chat.select_evidence", feature="chat")
def evidence_selection_node(state: ChatState) -> dict:
    evidence = state.get("retrieved_evidence", [])
    return {"selected_evidence": evidence}


@traced_node("studyai.chat.generate", feature="chat")
def answer_generation_node(state: ChatState) -> dict:
    llm = get_llm_provider()
    evidence = state.get("selected_evidence", [])
    query = state["user_request"]

    payload = {
        "evidence": [
            {"chunk_id": e["chunk_id"], "content": e["snippet"]} for e in evidence
        ]
    }

    prompt = Prompt(
        name="chat",
        version="v1",
        user="EVIDENCE_JSON:" + json.dumps(payload),
    )

    started = time.monotonic()
    result = llm.generate_structured(
        prompt=prompt,
        schema=ChatAnswer,
        request_id=f"chat:{state.get('session_id')}",
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

    answer = result.data.get("answer", "")
    cited_ids = result.data.get("cited_chunk_ids", [])

    by_id = {e["chunk_id"]: e for e in evidence}
    citations = []
    cited_contents = []
    for cid in cited_ids:
        ev = by_id.get(cid)
        if ev is None:
            continue
        cited_contents.append(ev["snippet"])
        citations.append({
            "source_type": ev["source_type"],
            "chunk_id": ev["chunk_id"],
            "document_id": ev["document_id"],
            "page_start": ev["page_start"],
            "page_end": ev["page_end"],
            "snippet": ev["snippet"],
            "rrf_score": round(ev["scores"]["rrf"], 6),
        })

    return {
        "answer": answer,
        "citations": citations,
        "cited_contents": cited_contents,
    }


@traced_node("studyai.chat.verify", feature="chat")
def citation_verification_node(state: ChatState) -> dict:
    answer = state.get("answer", "")
    cited_contents = state.get("cited_contents", [])
    status, score = EvidenceVerifier._classify(answer, cited_contents)
    return {
        "verification_status": status,
        "verification_score": score,
    }


@traced_node("studyai.chat.retry", feature="chat")
def retry_answer_node(state: ChatState) -> dict:
    llm = get_llm_provider()
    evidence = state.get("selected_evidence", state.get("retrieved_evidence", []))
    query = state["user_request"]

    payload = {
        "evidence": [
            {"chunk_id": e["chunk_id"], "content": e["snippet"]} for e in evidence
        ]
    }

    verification_details = (
        f"Previous answer was marked as {state.get('verification_status', 'unsupported')} "
        f"(score: {state.get('verification_score', 0.0)}). "
        "Please revise the answer to be better supported by the evidence."
    )

    prompt = Prompt(
        name="chat",
        version="v1",
        user="Previous answer feedback: "
        + verification_details
        + "\nEVIDENCE_JSON:"
        + json.dumps(payload),
    )

    started = time.monotonic()
    result = llm.generate_structured(
        prompt=prompt,
        schema=ChatAnswerRetry,
        request_id=f"chat:{state.get('session_id')}:retry",
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

    answer = result.data.get("answer", "")
    cited_ids = result.data.get("cited_chunk_ids", [])

    by_id = {e["chunk_id"]: e for e in evidence}
    citations = []
    cited_contents = []
    for cid in cited_ids:
        ev = by_id.get(cid)
        if ev is None:
            continue
        cited_contents.append(ev["snippet"])
        citations.append({
            "source_type": ev["source_type"],
            "chunk_id": ev["chunk_id"],
            "document_id": ev["document_id"],
            "page_start": ev["page_start"],
            "page_end": ev["page_end"],
            "snippet": ev["snippet"],
            "rrf_score": round(ev["scores"]["rrf"], 6),
        })

    return {
        "answer": answer,
        "citations": citations,
        "cited_contents": cited_contents,
        "retry_count": state.get("retry_count", 0) + 1,
    }


@traced_node("studyai.chat.format", feature="chat")
def format_response_node(state: ChatState) -> dict:
    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "verification_status": state.get("verification_status", "not_verified"),
        "verification_score": state.get("verification_score"),
    }
