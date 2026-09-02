"""Ask StudyAI Chat LangGraph workflow."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.state.chat_state import ChatState
from ai.tracing.decorators import traced_graph
from apps.chat.langgraph_nodes import (
    answer_generation_node,
    evidence_selection_node,
    format_response_node,
    retrieve_node,
    retrieve_web_node,
    retry_answer_node,
    route_query_node,
    date_time_node,
)

logger = logging.getLogger(__name__)


def _run_verification(state: ChatState) -> dict:
    from ai.langgraph.graphs.verification_graph import invoke_verification_graph
    from ai.langgraph.state.verification_state import VerificationState

    verification_state = VerificationState(
        content=state.get("answer", ""),
        cited_contents=state.get("cited_contents", []),
        verification_status="not_verified",
        verification_score=0.0,
        errors=[],
        execution_metadata={},
    )
    result = invoke_verification_graph(verification_state)
    return {
        "verification_status": result.get("verification_status", "not_verified"),
        "verification_score": result.get("verification_score", 0.0),
    }


def _branch_after_route(state: ChatState) -> str:
    route = state.get("route")
    if route == "date_time":
        return "date_time_node"
    if route == "conversational":
        return "answer_generation"
    if route == "general_knowledge":
        return "retrieve_web"
    # material route: retrieve from DB
    return "retrieve"


def _branch_after_verification(state: ChatState) -> str:
    route = state.get("route")
    if route in ("conversational", "date_time"):
        return "format_response"
    if state.get("verification_status") in ("supported", "partially_supported"):
        return "format_response"
    retry = state.get("retry_count", 0)
    if retry >= 1:
        return "format_response"
    return "retry_answer"


def build_chat_graph():
    graph = StateGraph(ChatState)

    graph.add_node("route_query", route_query_node)
    graph.add_node("date_time_node", date_time_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("retrieve_web", retrieve_web_node)
    graph.add_node("evidence_selection", evidence_selection_node)
    graph.add_node("answer_generation", answer_generation_node)
    graph.add_node("citation_verification", _run_verification)
    graph.add_node("retry_answer", retry_answer_node)
    graph.add_node("format_response", format_response_node)

    graph.set_entry_point("route_query")

    graph.add_conditional_edges(
        "route_query",
        _branch_after_route,
        {
            "retrieve": "retrieve",
            "retrieve_web": "retrieve_web",
            "date_time_node": "date_time_node",
            "answer_generation": "answer_generation",
        },
    )

    # Date/time path goes directly to answer generation
    graph.add_edge("date_time_node", "answer_generation")
    # Both retrieval paths converge on evidence_selection
    graph.add_edge("retrieve", "evidence_selection")
    graph.add_edge("retrieve_web", "evidence_selection")
    graph.add_edge("evidence_selection", "answer_generation")
    graph.add_edge("answer_generation", "citation_verification")

    graph.add_conditional_edges(
        "citation_verification",
        _branch_after_verification,
        {
            "format_response": "format_response",
            "retry_answer": "retry_answer",
        },
    )
    graph.add_edge("retry_answer", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()


chat_graph = build_chat_graph()


@traced_graph("studyai.chat.classic", feature="chat")
def invoke_chat_graph(initial_state: ChatState) -> ChatState:
    return chat_graph.invoke(initial_state)