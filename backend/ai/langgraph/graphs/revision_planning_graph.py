"""Revision Planning LangGraph workflow."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.state.revision_planning_state import RevisionPlanningState
from ai.tracing.decorators import traced_graph
from apps.revision.revision_planning_nodes import (
    build_plan_node,
    format_output_node,
    get_mastery_overview_node,
)

logger = logging.getLogger(__name__)


def build_revision_planning_graph():
    graph = StateGraph(RevisionPlanningState)

    graph.add_node("get_mastery_overview", get_mastery_overview_node)
    graph.add_node("build_plan", build_plan_node)
    graph.add_node("format_output", format_output_node)

    graph.set_entry_point("get_mastery_overview")
    graph.add_edge("get_mastery_overview", "build_plan")
    graph.add_edge("build_plan", "format_output")
    graph.add_edge("format_output", END)

    return graph.compile()


revision_planning_graph = build_revision_planning_graph()


@traced_graph("studyai.revision_planning", feature="revision_planning")
def invoke_revision_planning_graph(initial_state: RevisionPlanningState) -> RevisionPlanningState:
    return revision_planning_graph.invoke(initial_state)
