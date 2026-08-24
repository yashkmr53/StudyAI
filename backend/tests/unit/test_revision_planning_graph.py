"""Phase 7 Revision Planning graph tests."""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ai.langgraph.state.revision_planning_state import RevisionPlanningState
from ai.langgraph.graphs.revision_planning_graph import (
    build_revision_planning_graph,
)
from apps.revision.revision_planning_nodes import (
    build_plan_node,
    format_output_node,
    get_mastery_overview_node,
)


class MockProfile:
    def __init__(self, pk):
        self.pk = pk


class MockTag:
    def __init__(self, pk, stable_key, display_name):
        self.pk = pk
        self.stable_key = stable_key
        self.display_name = display_name


class TestRevisionPlanningGraphNodes(TestCase):
    def test_get_mastery_overview_node(self):
        with patch("apps.revision.revision_planning_nodes.Profile.objects.get") as mock_get, \
             patch("apps.revision.revision_planning_nodes.RevisionPlanningService.overview") as mock_overview:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_overview.return_value = {
                "tags": [
                    {"tag_id": "tag-1", "stable_key": "dijkstra", "display_name": "Dijkstra", "status": "weak", "mastery": 0.2, "attempt_count": 1, "last_assessed_at": "2024-01-01T00:00:00Z"},
                ],
                "assessed_count": 1,
                "not_assessed_count": 0,
            }

            state = RevisionPlanningState(
                profile_id="profile-1",
                subject_id=None,
                target_date=date.today().isoformat(),
                days_left=14,
                horizon=14,
                weights={},
                urgency=0.5,
                candidates=[],
                priorities=[],
                schedule=[],
                errors=[],
                execution_metadata={},
            )

            result = get_mastery_overview_node(state)
            self.assertIn("priorities", result)
            self.assertEqual(len(result["priorities"]), 1)

    def test_build_plan_node(self):
        with patch("apps.revision.revision_planning_nodes.Profile.objects.get") as mock_get, \
             patch("apps.revision.revision_planning_nodes.RevisionPlanningService.build_plan") as mock_build_plan:
            mock_profile = MockProfile("profile-1")
            mock_get.return_value = mock_profile
            mock_build_plan.return_value = {
                "target_date": "2024-01-15",
                "days_left": 14,
                "priorities": [
                    {"tag_id": "tag-1", "display_name": "Dijkstra", "status": "weak", "priority": 0.8},
                ],
                "schedule": [
                    {"date": "2024-01-01", "focus": ["Dijkstra"]},
                ],
            }

            state = RevisionPlanningState(
                profile_id="profile-1",
                subject_id=None,
                target_date=date(2024, 1, 15).isoformat(),
                days_left=14,
                horizon=14,
                weights={"weakness": 0.45, "urgency": 0.25, "failures": 0.20, "insufficient": 0.10},
                urgency=0.5,
                candidates=[],
                priorities=[],
                schedule=[],
                errors=[],
                execution_metadata={},
            )

            result = build_plan_node(state)
            self.assertIn("priorities", result)
            self.assertIn("schedule", result)
            self.assertEqual(len(result["priorities"]), 1)
            self.assertEqual(result["priorities"][0]["display_name"], "Dijkstra")

    def test_format_output_node(self):
        state = RevisionPlanningState(
            profile_id="profile-1",
            subject_id=None,
            target_date="2024-12-31",
            days_left=14,
            horizon=14,
            weights={},
            urgency=0.5,
            candidates=[],
            priorities=[{"tag_id": "tag-1", "display_name": "Dijkstra", "priority": 0.8}],
            schedule=[{"date": "2024-12-31", "focus": ["Dijkstra"]}],
            errors=[],
            execution_metadata={},
        )

        result = format_output_node(state)
        self.assertEqual(result["target_date"], "2024-12-31")
        self.assertEqual(result["days_left"], 14)
        self.assertEqual(len(result["priorities"]), 1)
        self.assertEqual(len(result["schedule"]), 1)


class TestRevisionPlanningGraphIntegration(TestCase):
    def test_graph_builds_successfully(self):
        graph = build_revision_planning_graph()
        self.assertIsNotNone(graph)
