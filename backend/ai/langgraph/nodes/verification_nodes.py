"""Verification graph node (reusable across features)."""
import logging

from ai.langgraph.state.verification_state import VerificationState
from ai.tracing.decorators import traced_node
from apps.ai_classroom.services import EvidenceVerifier

logger = logging.getLogger(__name__)


@traced_node("studyai.verification.evidence", feature="verification")
def verify_node(state: VerificationState, config=None) -> dict:
    status, score = EvidenceVerifier._classify(
        state["content"],
        state.get("cited_contents", []),
    )
    return {
        "verification_status": status,
        "verification_score": score,
    }
