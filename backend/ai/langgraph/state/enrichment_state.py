"""Typed state for the AI Enrichment LangGraph workflow."""
from typing import TypedDict, Optional, Any, List, Dict

from ai.langgraph.state.base_state import BaseStudyAIState


class EnrichmentState(BaseStudyAIState):
    document_id: str
    job_id: str
    user_chunks: List[Dict[str, Any]]
    reference_chunks: List[Dict[str, Any]]
    evidence_payload: Dict[str, Any]
    draft_result: Dict[str, Any]
    gaps_result: Dict[str, Any]
    fill_result: Dict[str, Any]
    all_blocks: List[Dict[str, Any]]
    stitched_blocks: List[Dict[str, Any]]
