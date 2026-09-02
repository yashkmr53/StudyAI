"""Chat graph nodes for Ask StudyAI LangGraph workflow."""
import json
import logging
import re
import time

from ai.langgraph.state.chat_state import ChatState
from ai.schemas.chat import ChatAnswer, ChatAnswerRetry
from ai.tracing.config import log_llm_call, log_retrieval
from ai.tracing.decorators import traced_node
from apps.ai_classroom.services import EvidenceVerifier
from apps.chat.models import ChatSession
from apps.retrieval.retrieval import RetrievalService
from providers.registry import get_llm_provider, get_web_search_provider
from providers.base import Prompt
from django.conf import settings

logger = logging.getLogger(__name__)

# Patterns indicating the user is asking about their own study material
_MATERIAL_PATTERNS = [
    r"\bmy\s+(notes?|materials?|docs?|documents?|studies?|course|textbook|book)\b",
    r"\b(from|in|according to)\s+my\b",
    r"\b(i|we)\s+(uploaded|wrote|studied|learned|covered)\b",
    r"\bmy\s+(dsa|algo|math|physics|chem|bio|cs)\b",
]

# Date/time patterns that should use runtime date/time
_DATE_TIME_PATTERNS = [
    r"^what('s| is) today'?s date$",
    r"^what date is it$",
    r"^what('s| is) the date$",
    r"^today'?s date$",
    r"^what day is it$",
    r"^what('s| is) the day$",
    r"^what time is it$",
    r"^what('s| is) the time$",
    r"^current date$",
    r"^current time$",
    r"^what's the date$",
    r"^date today$",
    r"^time now$",
]

# Conversational patterns (greetings, thanks, personal statements, questions)
_CONVERSATIONAL_PATTERNS = [
    r"^h[iy]$", r"^hello$", r"^hey$", r"^hi there$",
    r"^how (are|r) (you|u|doing)$", r"^good (morning|afternoon|evening)$",
    r"^what('s| is) up$", r"^sup$", r"^yo$", r"^greetings$",
    r"^thanks+$", r"^thank (you|u)$", r"^bye$", r"^goodbye$",
    r"^can you hear me$", r"^test$",
    # Personal statements and questions
    r"^my name is\b",
    r"^i am\b", r"^i'm\b",
    r"^what is my name\b", r"^what's my name\b",
    r"^do you know my name\b", r"^do you remember my name\b",
    r"^what did i (just )?tell you\b",
    r"^what did i (just )?say\b",
    r"^do you remember\b",
    r"^what is my favorite\b", r"^what's my favorite\b",
    r"^who am i\b", r"^tell me about me\b",
    # General conversational
    r"^how are you\b", r"^what can you do\b",
    r"^who are you\b", r"^tell me about yourself\b",
]


@traced_node("studyai.chat.route", feature="chat")
def route_query_node(state: ChatState) -> dict:
    """Classify the user query to decide retrieval strategy.

    Routing:
      - date_time: date/time questions → use runtime date/time, no retrieval
      - conversational: greetings, personal statements, thanks → no retrieval
      - material: user asks about their own notes/materials → retrieve from DB
      - general_knowledge: everything else → retrieve from web
    """
    query = (state.get("user_request") or "").strip().lower().rstrip("!?.,;:")

    # 1. Date/time: use runtime date/time, no retrieval
    for pat in _DATE_TIME_PATTERNS:
        if re.match(pat, query):
            return {"route": "date_time"}

    # 2. Conversational: no retrieval needed
    for pat in _CONVERSATIONAL_PATTERNS:
        if re.match(pat, query):
            return {"route": "conversational"}

    # 3. Material: user explicitly references their own study material
    for pat in _MATERIAL_PATTERNS:
        if re.search(pat, query):
            return {"route": "material"}

    # 4. General knowledge: use web retrieval
    return {"route": "general_knowledge"}


def _get_current_date_time() -> dict:
    """Get current date and time for date/time queries."""
    import datetime as _dt
    now = _dt.datetime.now()
    today = _dt.date.today()
    return {
        "date_iso": today.isoformat(),
        "date_formatted": today.strftime("%B %d, %Y"),
        "day_of_week": today.strftime("%A"),
        "time": now.strftime("%I:%M %p"),
        "timezone": str(now.astimezone().tzinfo) if now.astimezone().tzinfo else "local",
    }


@traced_node("studyai.chat.date_time", feature="chat")
def date_time_node(state: ChatState) -> dict:
    """Provide runtime date/time for date/time queries."""
    dt = _get_current_date_time()
    return {
        "current_date": dt["date_formatted"],
        "retrieved_evidence": [],
        "web_evidence": [],
    }


@traced_node("studyai.chat.retrieve", feature="chat")
def retrieve_node(state: ChatState) -> dict:
    """Retrieve evidence from the user's uploaded study material (DB/pgvector)."""
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


@traced_node("studyai.chat.retrieve_web", feature="chat")
def retrieve_web_node(state: ChatState) -> dict:
    """Retrieve evidence from the web for general-knowledge questions."""
    query = state.get("user_request", "")
    start = time.monotonic()

    provider = get_web_search_provider()
    max_results = getattr(settings, "WEB_SEARCH_MAX_RESULTS", 5)
    results = provider.search(query, max_results=max_results, request_id=f"chat:{state.get('session_id')}")

    latency_ms = int((time.monotonic() - start) * 1000)
    log_retrieval(
        query=query,
        profile_id=str(state.get("profile_id", "")),
        subject_id=None,
        k=max_results,
        results_count=len(results),
        latency_ms=latency_ms,
    )

    web_evidence = [r.as_dict() for r in results]
    return {"web_evidence": web_evidence}


@traced_node("studyai.chat.select_evidence", feature="chat")
def evidence_selection_node(state: ChatState) -> dict:
    """Select and merge evidence from both DB and web sources."""
    db_evidence = state.get("retrieved_evidence", [])
    web_evidence = state.get("web_evidence", [])

    # Tag each evidence with a stable internal citation ID the LLM can reference
    selected: list[dict] = []
    for e in db_evidence:
        e["citation_id"] = f"SRC-{len(selected) + 1:03d}"
        e["source_type"] = "database"
        selected.append(e)
    for e in web_evidence:
        e["citation_id"] = f"SRC-{len(selected) + 1:03d}"
        e["source_type"] = "web"
        selected.append(e)

    return {"selected_evidence": selected}


CHAT_SYSTEM_PROMPT = (
    "You are StudyAI, a helpful study-assistant chatbot. "
    "Use the CONVERSATION HISTORY to answer questions about previous exchanges. "
    "When evidence is provided, answer using that evidence and cite sources by their citation_id. "
    "When no evidence is provided (greetings, personal questions, conversation), "
    "respond conversationally using the conversation history and do NOT mention evidence or citations. "
    "Each evidence item has a citation_id (e.g. SRC-001). "
    "Reference sources by including their citation_id in cited_ids. "
    "Never invent document names, URLs, page numbers, or source IDs. "
    "Only use citation_ids that appear in the evidence list."
)


def _build_citations(evidence: list[dict], cited_ids: list[str]) -> tuple[list[dict], list[str]]:
    """Map cited citation IDs back to evidence dicts and build citation records.

    Only citation IDs that actually exist in the retrieved evidence are included.
    Citations referencing unknown IDs (e.g. hallucinated by the LLM) are
    silently dropped. Falls back to chunk_id when citation_id is absent.
    """
    by_id: dict[str, dict] = {}
    for e in evidence:
        if "citation_id" in e:
            by_id[e["citation_id"]] = e
        if "chunk_id" in e:
            by_id[e["chunk_id"]] = e

    citations: list[dict] = []
    cited_contents: list[str] = []
    seen_ids: set[str] = set()

    for cid in cited_ids:
        if cid in seen_ids:
            continue
        ev = by_id.get(cid)
        if ev is None:
            continue
        seen_ids.add(cid)
        src_id = f"src-{len(citations) + 1:03d}"
        cited_contents.append(ev.get("snippet", "") or ev.get("content", ""))

        if ev.get("source_type") == "web":
            citations.append({
                "source_id": src_id,
                "source_type": "web",
                "title": ev.get("title"),
                "url": ev.get("url"),
                "domain": ev.get("domain"),
                "snippet": ev.get("snippet", "")[:280],
                "verification_status": "supported",
                "verification_score": 1.0,
            })
        else:
            citations.append({
                "source_id": src_id,
                "source_type": "database",
                "chunk_id": ev.get("chunk_id"),
                "document_id": ev.get("document_id"),
                "document_title": ev.get("document_title"),
                "subject_name": ev.get("subject_name"),
                "page_start": ev.get("page_start"),
                "page_end": ev.get("page_end"),
                "snippet": ev.get("snippet", "")[:280],
                "rrf_score": round(ev.get("scores", {}).get("rrf", 0.0), 6),
                "url": None,
                "verification_status": "supported",
                "verification_score": 1.0,
            })

    return citations, cited_contents


@traced_node("studyai.chat.generate", feature="chat")
def answer_generation_node(state: ChatState) -> dict:
    llm = get_llm_provider()
    evidence = state.get("selected_evidence", [])
    query = state["user_request"]
    messages = state.get("messages", [])
    current_date = state.get("current_date")

    # Build evidence payload with citation_ids the LLM can reference
    payload = {
        "evidence": [
            {
                "citation_id": e.get("citation_id", f"SRC-{i + 1:03d}"),
                "content": e.get("snippet", "") or e.get("content", ""),
                "source_type": e.get("source_type", "database"),
                "document_title": e.get("document_title"),
                "title": e.get("title"),
                "url": e.get("url"),
                "page_start": e.get("page_start"),
                "page_end": e.get("page_end"),
            }
            for i, e in enumerate(evidence)
        ]
    }

    # Build conversation history string (excluding the current message)
    history_str = ""
    if messages:
        history_lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                history_lines.append(f"{role}: {content}")
        if history_lines:
            history_str = "CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

    # Build date/time context if available
    date_str = ""
    if current_date:
        date_str = f"CURRENT DATE/TIME: {current_date}\n\n"

    # Only include evidence section when there is actual evidence.
    # Sending empty EVIDENCE_JSON to a small local LLM causes it to
    # hallucinate that no information is available, even when the
    # conversation history contains the answer.
    if evidence:
        user = f"{date_str}{history_str}QUESTION: {query}\n\nEVIDENCE_JSON:" + json.dumps(payload)
    else:
        user = f"{date_str}{history_str}QUESTION: {query}"

    prompt = Prompt(
        name="chat",
        version="v1",
        system=CHAT_SYSTEM_PROMPT,
        user=user,
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
    # Support both cited_ids (new) and cited_chunk_ids (backward compat)
    cited_ids = result.data.get("cited_ids", []) or result.data.get("cited_chunk_ids", [])

    citations, cited_contents = _build_citations(evidence, cited_ids)

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
            {
                "citation_id": e.get("citation_id", f"SRC-{i + 1:03d}"),
                "content": e.get("snippet", "") or e.get("content", ""),
                "source_type": e.get("source_type", "database"),
                "document_title": e.get("document_title"),
                "title": e.get("title"),
                "url": e.get("url"),
                "page_start": e.get("page_start"),
                "page_end": e.get("page_end"),
            }
            for i, e in enumerate(evidence)
        ]
    }

    verification_details = (
        f"Previous answer was marked as {state.get('verification_status', 'unsupported')} "
        f"(score: {state.get('verification_score', 0.0)}). "
        "Please revise the answer to be better supported by the evidence."
    )

    if evidence:
        user = (
            "Previous answer feedback: "
            + verification_details
            + f"\n\nQUESTION: {query}\n\nEVIDENCE_JSON:"
            + json.dumps(payload)
        )
    else:
        user = (
            "Previous answer feedback: "
            + verification_details
            + f"\n\nQUESTION: {query}\n\n"
            "NOTE: No study material evidence is available for this question. "
            "Answer conversationally using conversation history only."
        )

    prompt = Prompt(
        name="chat",
        version="v1",
        system=CHAT_SYSTEM_PROMPT,
        user=user,
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
    cited_ids = result.data.get("cited_ids", []) or result.data.get("cited_chunk_ids", [])

    citations, cited_contents = _build_citations(evidence, cited_ids)

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
