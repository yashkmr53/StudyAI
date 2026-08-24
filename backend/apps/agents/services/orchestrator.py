"""Agent Orchestrator (Phase 1).

Core reasoning loop: intent analysis → tool selection → execution → observation → continue/finalize.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings

from providers.base import Prompt
from providers.registry import get_llm_provider

from apps.agents.tools import get_tool_registry
from apps.agents.prompts.agent_prompts import build_agent_system_prompt

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    tool: str
    arguments: dict
    result: dict
    latency_ms: int
    success: bool
    error: str | None = None


@dataclass
class AgentDecision:
    is_final_answer: bool
    tool_name: str | None = None
    tool_args: dict | None = None
    reasoning: str = ""
    final_answer: str = ""
    citations: list[dict] = field(default_factory=list)


@dataclass
class AgentResult:
    answer: str
    citations: list[dict]
    tool_calls: list[ToolCallRecord]
    iterations: int
    total_tokens: int
    total_latency_ms: int
    outcome: str
    trace_id: str
    verification_status: str | None = None
    verification_score: float | None = None


class AgentOrchestrator:
    """Orchestrates multi-step tool use for the StudyAI Agent."""

    def __init__(
        self,
        max_iterations: int | None = None,
        max_tool_calls: int | None = None,
        request_timeout_seconds: int | None = None,
        per_tool_timeout_seconds: int | None = None,
    ):
        self.max_iterations = max_iterations or getattr(settings, "AGENT_MAX_ITERATIONS", 5)
        self.max_tool_calls = max_tool_calls or getattr(settings, "AGENT_MAX_TOOL_CALLS", 10)
        self.request_timeout_seconds = request_timeout_seconds or getattr(settings, "AGENT_REQUEST_TIMEOUT_SECONDS", 60)
        self.per_tool_timeout_seconds = per_tool_timeout_seconds or getattr(settings, "AGENT_PER_TOOL_TIMEOUT_SECONDS", 30)

        self.registry = get_tool_registry()
        self.llm = get_llm_provider()

    def run(self, user_request: str, user, session, request_id: str) -> AgentResult:
        """Execute the agent orchestration loop."""
        started = time.monotonic()
        tool_calls: list[ToolCallRecord] = []
        iterations = 0
        total_tokens = 0
        retrieved_evidence_ids: list[str] = []

        system_prompt = build_agent_system_prompt()

        # Initial context for the LLM
        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
        ]

        while iterations < self.max_iterations:
            # Check wall-clock timeout
            if time.monotonic() - started > self.request_timeout_seconds:
                logger.warning("Agent request timeout: request_id=%s", request_id)
                break

            iterations += 1
            logger.info("Agent iteration: request_id=%s iteration=%d", request_id, iterations)

            # Get LLM decision
            decision = self._get_llm_decision(conversation, request_id)
            total_tokens += decision.tokens_used if hasattr(decision, "tokens_used") else 0

            if decision.is_final_answer:
                # Verify citations before returning
                verification_status, verification_score = self._verify_citations(
                    decision.final_answer, decision.citations, request_id
                )

                return AgentResult(
                    answer=decision.final_answer,
                    citations=decision.citations,
                    tool_calls=tool_calls,
                    iterations=iterations,
                    total_tokens=total_tokens,
                    total_latency_ms=int((time.monotonic() - started) * 1000),
                    outcome="success",
                    trace_id=request_id,
                    verification_status=verification_status,
                    verification_score=verification_score,
                )

            # Execute tool
            if decision.tool_name and decision.tool_args is not None:
                tool_record = self._execute_tool(
                    decision.tool_name,
                    decision.tool_args,
                    user,
                    request_id,
                )
                tool_calls.append(tool_record)

                # Collect evidence IDs for telemetry
                if tool_record.success and tool_record.result.get("results"):
                    for result in tool_record.result["results"]:
                        if "chunk_id" in result:
                            retrieved_evidence_ids.append(result["chunk_id"])

                # Add tool result to conversation
                conversation.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "tool": decision.tool_name,
                        "arguments": decision.tool_args,
                        "result": tool_record.result,
                        "success": tool_record.success,
                    }),
                })

                # Check tool call limit
                if len(tool_calls) >= self.max_tool_calls:
                    logger.warning("Agent max tool calls reached: request_id=%s", request_id)
                    break
            else:
                logger.warning("Agent: no tool selected and not final answer: request_id=%s", request_id)
                break

        # Limit reached — return partial result
        partial_answer = self._generate_partial_answer(conversation, request_id)
        return AgentResult(
            answer=partial_answer,
            citations=[],
            tool_calls=tool_calls,
            iterations=iterations,
            total_tokens=total_tokens,
            total_latency_ms=int((time.monotonic() - started) * 1000),
            outcome="limit_reached",
            trace_id=request_id,
        )

    def _get_llm_decision(self, conversation: list[dict], request_id: str) -> AgentDecision:
        """Get structured decision from LLM."""
        from providers.registry import get_llm_provider

        # Use structured output with a schema that matches AgentDecision
        # For now, we'll parse the JSON from the LLM response
        prompt = Prompt(
            name="agent_orchestrator",
            version="v1",
            system=conversation[0]["content"],
            user="\n".join(f"{msg['role']}: {msg['content']}" for msg in conversation[1:]),
        )

        # Use the mock provider's pattern — it returns structured data
        result = self.llm.generate_structured(
            prompt=prompt,
            schema=None,  # We'll parse JSON manually
            request_id=request_id,
        )

        # Parse the decision from result.data
        data = result.data
        total_tokens = getattr(result, "total_tokens", 0)

        if isinstance(data, dict) and "tool" in data:
            return AgentDecision(
                is_final_answer=False,
                tool_name=data.get("tool"),
                tool_args=data.get("arguments", {}),
                reasoning=data.get("reasoning", ""),
                tokens_used=total_tokens,
            )
        elif isinstance(data, dict) and "final_answer" in data:
            return AgentDecision(
                is_final_answer=True,
                final_answer=data.get("final_answer", ""),
                citations=data.get("citations", []),
                reasoning=data.get("reasoning", ""),
                tokens_used=total_tokens,
            )
        else:
            # Fallback: try to extract from text
            return self._parse_fallback(data, total_tokens)

    def _parse_fallback(self, data: dict, tokens: int) -> AgentDecision:
        """Fallback parsing for unexpected LLM output format."""
        # Try to find tool call or final answer in various formats
        if isinstance(data, dict):
            if "answer" in data:
                return AgentDecision(
                    is_final_answer=True,
                    final_answer=data.get("answer", ""),
                    citations=data.get("citations", []),
                    reasoning="fallback",
                    tokens_used=tokens,
                )
        return AgentDecision(
            is_final_answer=True,
            final_answer="I apologize, but I encountered an issue processing your request.",
            citations=[],
            reasoning="fallback_parse_error",
            tokens_used=tokens,
        )

    def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict,
        user,
        request_id: str,
    ) -> ToolCallRecord:
        """Execute a single tool with timeout and error handling."""
        tool_started = time.monotonic()

        try:
            tool = self.registry.get(tool_name)
            input_model = tool.metadata.input_schema(**tool_args)

            # Execute with timeout (simulated via tool's internal timeout)
            result = tool.execute(input_model, user=user, request_id=request_id)

            latency_ms = int((time.monotonic() - tool_started) * 1000)
            result.latency_ms = latency_ms

            return ToolCallRecord(
                tool=tool_name,
                arguments=tool_args,
                result=result.model_dump(),
                latency_ms=latency_ms,
                success=result.success,
                error=result.error,
            )

        except KeyError:
            latency_ms = int((time.monotonic() - tool_started) * 1000)
            logger.error("Unknown tool: %s", tool_name)
            return ToolCallRecord(
                tool=tool_name,
                arguments=tool_args,
                result={},
                latency_ms=latency_ms,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - tool_started) * 1000)
            logger.exception("Tool execution failed: %s", tool_name)
            return ToolCallRecord(
                tool=tool_name,
                arguments=tool_args,
                result={},
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )

    def _verify_citations(
        self,
        answer: str,
        citations: list[dict],
        request_id: str,
    ) -> tuple[str | None, float | None]:
        """Verify the final answer against cited sources."""
        if not citations:
            return None, None

        from apps.ai_classroom.services import EvidenceVerifier

        # Prepare source refs for verification
        source_refs = []
        for citation in citations:
            source_refs.append({
                "chunk_id": citation.get("chunk_id"),
                "document_id": citation.get("document_id"),
                "page_number": citation.get("page_start"),
                "revision_id": citation.get("revision_id"),
            })

        try:
            status, score = EvidenceVerifier.verify(answer, source_refs)
            return status, score
        except Exception as exc:  # noqa: BLE001
            logger.warning("Citation verification failed: %s", exc)
            return None, None

    def _generate_partial_answer(self, conversation: list[dict], request_id: str) -> str:
        """Generate a partial answer when limits are reached."""
        # Extract any tool results from conversation
        evidence_parts = []
        for msg in conversation:
            if msg["role"] == "assistant":
                try:
                    data = json.loads(msg["content"])
                    if "result" in data and data["result"].get("results"):
                        for result in data["result"]["results"]:
                            if "snippet" in result:
                                evidence_parts.append(result["snippet"][:200])
                except (json.JSONDecodeError, KeyError):
                    pass

        if evidence_parts:
            return f"Based on the available information: {' '.join(evidence_parts[:3])}"
        return "I was unable to complete the analysis within the allowed steps. Please try a more specific question."