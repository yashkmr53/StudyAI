"""Adaptive Test LangGraph workflow."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.state.adaptive_test_state import AdaptiveTestState
from ai.tracing.decorators import traced_graph
from apps.tests.adaptive_test_nodes import (
    create_test_node,
    format_output_node,
    generate_questions_node,
    get_mastery_node,
    identify_weak_topics_node,
    retrieve_notes_node,
    select_questions_node,
)

logger = logging.getLogger(__name__)


def _branch_after_identify_weak(state: AdaptiveTestState) -> str:
    return "retrieve"


def build_adaptive_test_graph():
    graph = StateGraph(AdaptiveTestState)

    graph.add_node("get_mastery", get_mastery_node)
    graph.add_node("identify_weak", identify_weak_topics_node)
    graph.add_node("retrieve", retrieve_notes_node)
    graph.add_node("generate", generate_questions_node)
    graph.add_node("select", select_questions_node)
    graph.add_node("create_test", create_test_node)
    graph.add_node("format", format_output_node)

    graph.set_entry_point("get_mastery")
    graph.add_edge("get_mastery", "identify_weak")

    graph.add_conditional_edges(
        "identify_weak",
        _branch_after_identify_weak,
        {
            "retrieve": "retrieve",
        },
    )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "select")
    graph.add_edge("select", "create_test")
    graph.add_edge("create_test", "format")
    graph.add_edge("format", END)

    return graph.compile()


adaptive_test_graph = build_adaptive_test_graph()


@traced_graph("studyai.adaptive_test", feature="adaptive_test")
def invoke_adaptive_test_graph(initial_state: AdaptiveTestState) -> AdaptiveTestState:
    return adaptive_test_graph.invoke(initial_state)
