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
    user = Profile.objects.get(pk=state["profile_id"]).user
    tool_calls = state.get("tool_calls", [])
    iterations = state.get("iterations", 0)

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
        result = tool.execute(input_model, user=user, request_id=f"agent:{state.get('session_id')}")
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


@traced_node("studyai.agent.format_response", feature="agent")
def format_response_node(state: AgentState, config=None) -> dict:
    tool_calls = state.get("tool_calls", [])
    last_result = state.get("last_tool_result", {})

    evidence_parts = []
    citations = []

    for tc in tool_calls:
        result_data = tc.get("result", {})
        if isinstance(result_data, dict):
            for r in result_data.get("results", []):
                if "snippet" in r:
                    evidence_parts.append(r["snippet"][:200])
                if "chunk_id" in r:
                    citations.append({
                        "chunk_id": r.get("chunk_id"),
                        "source_type": r.get("source_type", "note"),
                        "page_start": r.get("page_start"),
                        "page_end": r.get("page_end"),
                        "snippet": r.get("snippet", "")[:200],
                    })

    if evidence_parts:
        answer = f"Based on the available information: {' '.join(evidence_parts[:3])}"
    elif last_result.get("success") and last_result.get("result", {}).get("results"):
        snippets = [r.get("snippet", "")[:200] for r in last_result["result"]["results"] if "snippet" in r]
        answer = f"Based on the search results: {' '.join(snippets[:3])}"
    else:
        answer = "I was unable to complete the analysis within the allowed steps. Please try a more specific question."

    return {
        "answer": answer,
        "citations": citations,
        "verification_status": "not_verified",
        "verification_score": 0.0,
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
