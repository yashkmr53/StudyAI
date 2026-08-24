"""Question Generation LangGraph workflow."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.state.question_generation_state import QuestionGenerationState
from ai.tracing.decorators import traced_graph
from apps.questions.question_generation_nodes import (
    generate_questions_node,
    persist_questions_node,
    retrieve_chunks_node,
    validate_questions_node,
)

logger = logging.getLogger(__name__)


def _run_verification(state: QuestionGenerationState) -> dict:
    from ai.langgraph.graphs.verification_graph import invoke_verification_graph
    from ai.langgraph.state.verification_state import VerificationState

    verified = []
    for q in state.get("validated_questions", []):
        if not q.get("is_valid", False):
            verified.append({**q, "verification_status": "skipped"})
            continue
        verification_state = VerificationState(
            content=q.get("prompt", ""),
            cited_contents=[q.get("prompt", "")],
            verification_status="not_verified",
            verification_score=0.0,
            errors=[],
            execution_metadata={},
        )
        result = invoke_verification_graph(verification_state)
        verified.append({
            **q,
            "verification_status": result.get("verification_status", "not_verified"),
            "verification_score": result.get("verification_score", 0.0),
        })
    return {"verified_questions": verified}


def _branch_after_validation(state: QuestionGenerationState) -> str:
    validated = state.get("validated_questions", [])
    invalid = [q for q in validated if not q.get("is_valid", False)]
    if invalid:
        return "persist"
    return "verify"


def build_question_generation_graph():
    graph = StateGraph(QuestionGenerationState)

    graph.add_node("retrieve", retrieve_chunks_node)
    graph.add_node("generate", generate_questions_node)
    graph.add_node("validate", validate_questions_node)
    graph.add_node("verify", _run_verification)
    graph.add_node("persist", persist_questions_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "validate")

    graph.add_conditional_edges(
        "validate",
        _branch_after_validation,
        {
            "verify": "verify",
            "persist": "persist",
        },
    )
    graph.add_edge("verify", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


question_generation_graph = build_question_generation_graph()


@traced_graph("studyai.question_generation", feature="question_generation")
def invoke_question_generation_graph(initial_state: QuestionGenerationState) -> QuestionGenerationState:
    return question_generation_graph.invoke(initial_state)
