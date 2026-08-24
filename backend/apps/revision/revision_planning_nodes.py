"""Revision planning graph nodes."""
import logging
from datetime import date, timedelta

from ai.langgraph.state.revision_planning_state import RevisionPlanningState
from ai.tracing.decorators import traced_node
from apps.profiles.models import Profile
from apps.revision.services import RevisionPlanningService, timezone_now
from apps.tests.models import MasteryScore, TestAttempt

logger = logging.getLogger(__name__)


@traced_node("studyai.revision_planning.overview", feature="revision_planning")
def get_mastery_overview_node(state: RevisionPlanningState, config=None) -> dict:
    profile = Profile.objects.get(pk=state["profile_id"])
    overview = RevisionPlanningService.overview(profile)
    return {"priorities": overview.get("tags", [])}


@traced_node("studyai.revision_planning.build", feature="revision_planning")
def build_plan_node(state: RevisionPlanningState, config=None) -> dict:
    profile = Profile.objects.get(pk=state["profile_id"])
    target_date = date.fromisoformat(state["target_date"])
    subject = None
    if state.get("subject_id"):
        from apps.subjects.models import Subject
        try:
            subject = Subject.objects.get(pk=state["subject_id"], profile=profile)
        except (Subject.DoesNotExist, ValueError, TypeError):
            subject = None

    plan = RevisionPlanningService.build_plan(profile, subject, target_date)
    return {
        "priorities": plan.get("priorities", []),
        "schedule": plan.get("schedule", []),
        "days_left": plan.get("days_left", 0),
    }


@traced_node("studyai.revision_planning.format", feature="revision_planning")
def format_output_node(state: RevisionPlanningState, config=None) -> dict:
    return {
        "target_date": state.get("target_date"),
        "days_left": state.get("days_left", 0),
        "priorities": state.get("priorities", []),
        "schedule": state.get("schedule", []),
    }
