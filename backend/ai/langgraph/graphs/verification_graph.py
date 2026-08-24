"""Reusable Evidence Verification LangGraph sub-graph."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.nodes.verification_nodes import verify_node
from ai.langgraph.state.verification_state import VerificationState
from ai.tracing.decorators import traced_graph

logger = logging.getLogger(__name__)


def build_verification_graph():
    graph = StateGraph(VerificationState)
    graph.add_node("verify", verify_node)
    graph.set_entry_point("verify")
    graph.add_edge("verify", END)
    return graph.compile()


verification_graph = build_verification_graph()


@traced_graph("studyai.verification", feature="verification")
def invoke_verification_graph(initial_state: VerificationState) -> VerificationState:
    return verification_graph.invoke(initial_state)
