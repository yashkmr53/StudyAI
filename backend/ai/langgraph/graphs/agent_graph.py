"""Agentic LangGraph workflow."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.state.agent_state import AgentState
from ai.tracing.decorators import traced_graph
from ai.langgraph.nodes.agent_nodes import (
    analyze_request_node,
    execute_tool_node,
    finalize_node,
    format_response_node,
    select_tool_node,
)

logger = logging.getLogger(__name__)


def _branch_after_tool_execution(state: AgentState) -> str:
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 5)
    tool_calls = state.get("tool_calls", [])
    max_tool_calls = state.get("max_tool_calls", 10)

    if iterations >= max_iterations or len(tool_calls) >= max_tool_calls:
        return "format_response"
    return "select_tool"


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("analyze", analyze_request_node)
    graph.add_node("select_tool", select_tool_node)
    graph.add_node("execute_tool", execute_tool_node)
    graph.add_node("format_response", format_response_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "select_tool")
    graph.add_edge("select_tool", "execute_tool")

    graph.add_conditional_edges(
        "execute_tool",
        _branch_after_tool_execution,
        {
            "select_tool": "select_tool",
            "format_response": "format_response",
        },
    )
    graph.add_edge("format_response", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


agent_graph = build_agent_graph()


@traced_graph("studyai.agent", feature="agent")
def invoke_agent_graph(initial_state: AgentState) -> AgentState:
    return agent_graph.invoke(initial_state)
