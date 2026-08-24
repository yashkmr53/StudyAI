"""AI Enrichment LangGraph workflow."""
import logging

from langgraph.graph import END, StateGraph

from ai.langgraph.state.enrichment_state import EnrichmentState
from ai.tracing.decorators import traced_graph
from apps.ai_classroom.enrichment_nodes import (
    citation_stitch_node,
    draft_node,
    format_output_node,
    gap_detection_node,
    gap_fill_node,
    retrieve_chunks_node,
)

logger = logging.getLogger(__name__)


def _run_verification(state: EnrichmentState) -> dict:
    from ai.langgraph.graphs.verification_graph import invoke_verification_graph
    from ai.langgraph.state.verification_state import VerificationState

    stitched = state.get("stitched_blocks", [])
    verified = []
    for item in stitched:
        refs = item.get("refs", [])
        cited_contents = [ref.get("content", "") for ref in refs]
        verification_state = VerificationState(
            content=item.get("content", ""),
            cited_contents=cited_contents,
            verification_status="not_verified",
            verification_score=0.0,
            errors=[],
            execution_metadata={},
        )
        result = invoke_verification_graph(verification_state)
        verified.append({
            "index": item["index"],
            **item,
            "status": result.get("verification_status", "not_verified"),
            "score": result.get("verification_score", 0.0),
        })
    return {"stitched_blocks": verified}


def _branch_after_gap_detection(state: EnrichmentState) -> str:
    gaps = state.get("gaps_result", {}).get("gaps", [])
    if gaps:
        return "gap_fill"
    return "citation_stitch"


def build_enrichment_graph():
    graph = StateGraph(EnrichmentState)

    graph.add_node("retrieve", retrieve_chunks_node)
    graph.add_node("draft", draft_node)
    graph.add_node("gap_detection", gap_detection_node)
    graph.add_node("gap_fill", gap_fill_node)
    graph.add_node("citation_stitch", citation_stitch_node)
    graph.add_node("evidence_verification", _run_verification)
    graph.add_node("format_output", format_output_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "gap_detection")

    graph.add_conditional_edges(
        "gap_detection",
        _branch_after_gap_detection,
        {
            "gap_fill": "gap_fill",
            "citation_stitch": "citation_stitch",
        },
    )
    graph.add_edge("gap_fill", "citation_stitch")
    graph.add_edge("citation_stitch", "evidence_verification")
    graph.add_edge("evidence_verification", "format_output")
    graph.add_edge("format_output", END)

    return graph.compile()


enrichment_graph = build_enrichment_graph()


@traced_graph("studyai.enrichment", feature="enrichment")
def invoke_enrichment_graph(initial_state: EnrichmentState) -> EnrichmentState:
    return enrichment_graph.invoke(initial_state)
