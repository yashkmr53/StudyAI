"""Agentic LangGraph nodes."""
import hashlib
import json
import logging
import time

from ai.langgraph.state.agent_state import AgentState
from ai.tracing.decorators import traced_node
from apps.agents.tools import get_tool_registry
from apps.agents.tools.base import ToolInput, BaseTool
from apps.profiles.models import Profile
from providers.registry import get_llm_provider
from providers.base import Prompt

logger = logging.getLogger(__name__)


def _build_tool_schemas() -> dict:
    registry = get_tool_registry()
    tools = registry.list_tools()
    schemas = {}
    for tool in tools:
        input_schema = tool.metadata.input_schema.model_json_schema()
        schemas[tool.metadata.name] = {
            "description": tool.metadata.description,
            "input_schema": input_schema,
        }
    return schemas


def _detect_duplicate_tool_call(tool_calls: list[dict], new_tool_name: str, new_args: dict) -> bool:
    for tc in tool_calls:
        if tc.get("tool") == new_tool_name and tc.get("arguments") == new_args:
            return True
    return False


@traced_node("studyai.agent.analyze", feature="agent")
def analyze_request_node(state: AgentState, config=None) -> dict:
    profile = Profile.objects.get(pk=state["profile_id"])
    tool_schemas = _build_tool_schemas()

    return {
        "available_tools": tool_schemas,
        "retrieved_evidence": [],
        "selected_evidence": [],
        "tool_calls": [],
        "iterations": 0,
        "errors": [],
        "execution_metadata": {"profile_id": state["profile_id"]},
    }


@traced_node("studyai.agent.select_tool", feature="agent")
def select_tool_node(state: AgentState, config=None) -> dict:
    from apps.agents.prompts.agent_prompts import AGENT_SYSTEM_PROMPT

    available_tools = state.get("available_tools", {})
    tool_descriptions = json.dumps(available_tools, indent=2)

    system_prompt = AGENT_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)
    user_request = state["user_request"]
    tool_calls = state.get("tool_calls", [])

    if tool_calls:
        history = "\n".join([
            f"Tool: {tc.get('tool')}\nArguments: {json.dumps(tc.get('arguments', {}))}\nResult: {json.dumps(tc.get('result', {}))[:500]}"
            for tc in tool_calls[-3:]
        ])
        user_request = f"Previous tool calls:\n{history}\n\nOriginal request: {user_request}"

    prompt = Prompt(
        name="agent_orchestrator",
        version="v1",
        system=system_prompt,
        user=user_request,
    )

    llm = get_llm_provider()
    started = time.monotonic()
    result = llm.generate_structured(
        prompt=prompt,
        request_id=f"agent:{state.get('session_id')}:select",
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    tool_call = {
        "tool": result.data.get("tool"),
        "arguments": result.data.get("arguments", {}),
        "reasoning": result.data.get("reasoning", ""),
        "latency_ms": latency_ms,
        "model": result.model,
    }

    return {"tool_call": tool_call}


@traced_node("studyai.agent.execute_tool", feature="agent")
def execute_tool_node(state: AgentState, config=None) -> dict:
    tool_call = state.get("tool_call", {})
    tool_name = tool_call.get("tool")
    tool_args = tool_call.get("arguments", {})
    profile = Profile.objects.get(pk=state["profile_id"])
    user = profile.user
    tool_calls = state.get("tool_calls", [])
    iterations = state.get("iterations", 0)

    if not tool_name:
        return {
            "tool_calls": tool_calls,
            "iterations": iterations + 1,
            "last_tool_result": {
                "tool": None,
                "arguments": {},
                "result": {},
                "latency_ms": 0,
                "success": False,
                "error": "No tool selected",
            },
        }

    if _detect_duplicate_tool_call(tool_calls, tool_name, tool_args):
        return {
            "tool_calls": tool_calls,
            "iterations": iterations + 1,
            "last_tool_result": {
                "tool": tool_name,
                "arguments": tool_args,
                "result": {},
                "latency_ms": 0,
                "success": False,
                "error": "Duplicate tool call detected",
            }
        }

    registry = get_tool_registry()
    tool = registry.get(tool_name)

    started = time.monotonic()
    try:
        input_model = tool.metadata.input_schema(**tool_args)
        result = tool.execute(
            input_model,
            user=user,
            request_id=f"agent:{state.get('session_id')}",
            profile=profile,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        result.latency_ms = latency_ms

        tool_record = {
            "tool": tool_name,
            "arguments": tool_args,
            "result": result.model_dump(),
            "latency_ms": latency_ms,
            "success": result.success,
            "error": result.error,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        tool_record = {
            "tool": tool_name,
            "arguments": tool_args,
            "result": {},
            "latency_ms": latency_ms,
            "success": False,
            "error": str(exc),
        }

    return {
        "tool_calls": tool_calls + [tool_record],
        "iterations": iterations + 1,
        "last_tool_result": tool_record,
    }


_AGENT_SYNTHESIS_SYSTEM_PROMPT = (
    "You are StudyAI Agent. Synthesize a clear, concise, grounded answer from the "
    "retrieved tool results and cite supporting sources using their citation_id values."
)


def _format_citation(raw: dict, src_id: str) -> dict | None:
    """Build a normalized citation entry from a search/web tool result item."""
    snippet = (raw.get("snippet") or raw.get("content") or "")[:200]
    if "chunk_id" in raw:
        return {
            "source_id": src_id,
            "source_type": "database",
            "chunk_id": raw.get("chunk_id"),
            "document_id": raw.get("document_id"),
            "document_title": raw.get("document_title"),
            "subject_name": raw.get("subject_name"),
            "page_start": raw.get("page_start"),
            "page_end": raw.get("page_end"),
            "snippet": snippet,
            "url": None,
        }
    if raw.get("url"):
        return {
            "source_id": src_id,
            "source_type": "web",
            "title": raw.get("title"),
            "url": raw.get("url"),
            "domain": raw.get("domain"),
            "snippet": snippet,
        }
    return None


def _collect_tool_evidence(tool_calls: list[dict], last_result: dict) -> dict:
    """Extract normalized evidence payload, raw snippets, and citations from tool runs."""
    records = tool_calls if tool_calls else ([last_result] if last_result.get("success") else [])
    evidence_payload: list[dict] = []
    raw_snippets: list[str] = []
    by_cit_id: dict[str, tuple[dict | None, str]] = {}
    all_items: list[tuple[dict | None, str]] = []

    for tc in records:
        result_data = tc.get("result", {})
        if not isinstance(result_data, dict):
            continue

        if "results" in result_data and isinstance(result_data["results"], list):
            for r in result_data["results"]:
                if not isinstance(r, dict):
                    continue
                text = r.get("snippet") or r.get("content") or ""
                if not text:
                    continue
                cit_id = f"SRC-{len(evidence_payload) + 1:03d}"
                cit_entry = _format_citation(r, cit_id)
                evidence_payload.append({
                    "citation_id": cit_id,
                    "content": text,
                    "snippet": text[:200],
                    "source_type": cit_entry["source_type"] if cit_entry else "database",
                    "chunk_id": r.get("chunk_id"),
                    "document_id": r.get("document_id"),
                    "document_title": r.get("document_title"),
                    "subject_name": r.get("subject_name"),
                    "page_start": r.get("page_start"),
                    "page_end": r.get("page_end"),
                    "title": r.get("title"),
                    "url": r.get("url"),
                })
                raw_snippets.append(text[:200])
                by_cit_id[cit_id] = (cit_entry, text)
                all_items.append((cit_entry, text))
        elif tc.get("success", True):
            useful = {
                k: v
                for k, v in result_data.items()
                if k not in ("success", "error", "latency_ms") and v not in (None, [], {})
            }
            if useful:
                summary = json.dumps(useful, default=str)[:800]
                cit_id = f"SRC-{len(evidence_payload) + 1:03d}"
                evidence_payload.append({
                    "citation_id": cit_id,
                    "tool": tc.get("tool"),
                    "content": summary,
                })
                raw_snippets.append(summary[:200])
                by_cit_id[cit_id] = (None, summary)
                all_items.append((None, summary))

    return {
        "evidence_payload": evidence_payload,
        "raw_snippets": raw_snippets,
        "by_cit_id": by_cit_id,
        "all_items": all_items,
    }


def _select_citations(items: list[tuple[dict | None, str]]) -> tuple[list[dict], list[str]]:
    """Renumber kept citations sequentially and return paired cited texts."""
    citations: list[dict] = []
    cited_contents: list[str] = []
    for cit, text in items:
        cited_contents.append(text)
        if cit is not None:
            numbered = dict(cit)
            numbered["source_id"] = f"src-{len(citations) + 1:03d}"
            citations.append(numbered)
    return citations, cited_contents


def _verify_agent_answer(state: AgentState, answer: str, cited_contents: list[str]) -> tuple[str, float]:
    """Run the reusable EvidenceVerifier graph against cited evidence contents."""
    from ai.langgraph.graphs.verification_graph import invoke_verification_graph
    from ai.langgraph.state.verification_state import VerificationState

    ver_result = invoke_verification_graph(
        VerificationState(
            user_request=state.get("user_request", ""),
            profile_id=str(state.get("profile_id", "")),
            subject_id=state.get("subject_id"),
            session_id=state.get("session_id"),
            errors=[],
            execution_metadata={},
            content=answer,
            cited_contents=cited_contents,
            verification_status="not_verified",
            verification_score=0.0,
        )
    )
    return (
        ver_result.get("verification_status", "not_verified"),
        float(ver_result.get("verification_score") or 0.0),
    )


@traced_node("studyai.agent.format_response", feature="agent")
def format_response_node(state: AgentState, config=None) -> dict:
    from ai.schemas.chat import ChatAnswer

    tool_calls = state.get("tool_calls", [])
    last_result = state.get("last_tool_result", {})
    collected = _collect_tool_evidence(tool_calls, last_result)
    evidence_payload = collected["evidence_payload"]
    raw_snippets = collected["raw_snippets"]
    by_cit_id = collected["by_cit_id"]
    all_items = collected["all_items"]

    user_request = state.get("user_request", "")
    if evidence_payload:
        user_text = f"QUESTION: {user_request}\n\nEVIDENCE_JSON:{json.dumps({'evidence': evidence_payload})}"
    else:
        user_text = f"QUESTION: {user_request}"

    citations, cited_contents = _select_citations(all_items)

    try:
        llm = get_llm_provider()
        result = llm.generate_structured(
            prompt=Prompt(
                name="chat",
                version="v1",
                system=_AGENT_SYNTHESIS_SYSTEM_PROMPT,
                user=user_text,
            ),
            schema=ChatAnswer,
            request_id=f"agent:{state.get('session_id')}:format",
        )
        data = result.data if isinstance(result.data, dict) else {}
        answer = (data.get("answer") or "").strip()
        if not answer:
            raise ValueError("LLM returned empty answer during agent response synthesis")

        cited_ids = data.get("cited_ids", []) or data.get("cited_chunk_ids", []) or []
        matched = [by_cit_id[cid] for cid in dict.fromkeys(cited_ids) if cid in by_cit_id]
        if matched:
            citations, cited_contents = _select_citations(matched)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agent response LLM synthesis failed, using snippet fallback: %s", exc)
        if raw_snippets:
            answer = f"LLM synthesis failed (fallback to retrieved results): {' '.join(raw_snippets[:3])}"
        else:
            answer = (
                "LLM synthesis failed (fallback mode): "
                "I was unable to complete the analysis within the allowed steps. "
                "Please try a more specific question."
            )

    verification_status, verification_score = _verify_agent_answer(
        state, answer, cited_contents
    )

    return {
        "answer": answer,
        "citations": citations,
        "verification_status": verification_status,
        "verification_score": verification_score,
    }


@traced_node("studyai.agent.finalize", feature="agent")
def finalize_node(state: AgentState, config=None) -> dict:
    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "verification_status": state.get("verification_status", "not_verified"),
        "verification_score": state.get("verification_score", 0.0),
        "tool_calls": state.get("tool_calls", []),
        "iterations": state.get("iterations", 0),
    }
