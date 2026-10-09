"""Tests for AgentViewSet and Agentic Chat endpoints (POST /api/v1/chat/ and POST /api/v1/agents/chat/)."""
from django.test import TestCase

from apps.accounts.models import User
from apps.chat.models import ChatMessage, ChatSession
from apps.profiles.models import Profile
from tests.api.utils import authenticated_client


class AgentChatApiTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.alice_user = User.objects.get(email="alice@example.com")
        self.bob_user = User.objects.get(email="bob@example.com")

        self.alice_profile_1 = Profile.objects.filter(user=self.alice_user).first()
        # Create a second profile for Alice to test multi-profile resolution
        self.alice_profile_2 = Profile.objects.create(
            user=self.alice_user,
            name="Alice Profile 2",
        )
        self.bob_profile = Profile.objects.filter(user=self.bob_user).first()

        self.alice_session_1 = ChatSession.objects.create(
            profile=self.alice_profile_1,
            title="Session 1",
        )
        self.alice_session_2 = ChatSession.objects.create(
            profile=self.alice_profile_2,
            title="Session 2",
        )
        self.bob_session = ChatSession.objects.create(
            profile=self.bob_profile,
            title="Bob Session",
        )

    def test_tools_listing_endpoints(self):
        """Both /api/v1/tools/ and /api/v1/agents/tools/ return available tools."""
        res1 = self.alice.get("/api/v1/tools/")
        self.assertEqual(res1.status_code, 200)
        self.assertIsInstance(res1.json(), list)
        tool_names_1 = [t["name"] for t in res1.json()]
        self.assertIn("search_notes", tool_names_1)

        res2 = self.alice.get("/api/v1/agents/tools/")
        self.assertEqual(res2.status_code, 200)
        tool_names_2 = [t["name"] for t in res2.json()]
        self.assertEqual(tool_names_1, tool_names_2)

    def test_agent_chat_direct_endpoint_success(self):
        """POST /api/v1/chat/ successfully processes request, creates messages, and returns 201."""
        response = self.alice.post(
            "/api/v1/chat/",
            {
                "session_id": str(self.alice_session_1.id),
                "content": "Can you summarize Dijkstra algorithm?",
            },
            content_type="application/json",
            HTTP_X_PROFILE_ID=str(self.alice_profile_1.id),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("user", data)
        self.assertIn("assistant", data)
        self.assertEqual(data["user"]["role"], "user")
        self.assertEqual(data["assistant"]["role"], "assistant")
        self.assertTrue(data["assistant"]["content"])
        self.assertIn("tool_calls", data["assistant"])

        # Verify DB messages persisted
        messages = ChatMessage.objects.filter(session=self.alice_session_1).order_by("created_at")
        self.assertEqual(messages.count(), 2)
        self.assertEqual(messages[0].role, ChatMessage.Role.USER)
        self.assertEqual(messages[1].role, ChatMessage.Role.ASSISTANT)

    def test_agent_chat_prefixed_endpoint_success(self):
        """POST /api/v1/agents/chat/ (used by frontend agentApi) returns 201."""
        response = self.alice.post(
            "/api/v1/agents/chat/",
            {
                "session_id": str(self.alice_session_1.id),
                "content": "Help me study graphs",
            },
            content_type="application/json",
            HTTP_X_PROFILE_ID=str(self.alice_profile_1.id),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["assistant"]["role"], "assistant")

    def test_multi_profile_user_resolution(self):
        """User with multiple profiles does not trigger MultipleObjectsReturned."""
        response = self.alice.post(
            "/api/v1/chat/",
            {
                "session_id": str(self.alice_session_2.id),
                "content": "Test multi profile",
            },
            content_type="application/json",
            HTTP_X_PROFILE_ID=str(self.alice_profile_2.id),
        )
        self.assertEqual(response.status_code, 201)

    def test_active_profile_isolation_within_same_user(self):
        """Session belonging to Profile 2 cannot be accessed when active profile is Profile 1."""
        response = self.alice.post(
            "/api/v1/chat/",
            {
                "session_id": str(self.alice_session_2.id),
                "content": "Try to cross profile boundary",
            },
            content_type="application/json",
            HTTP_X_PROFILE_ID=str(self.alice_profile_1.id),  # active profile is profile 1
        )
        self.assertEqual(response.status_code, 404)

    def test_tenant_isolation_between_different_users(self):
        """Alice cannot target Bob's session."""
        response = self.alice.post(
            "/api/v1/chat/",
            {
                "session_id": str(self.bob_session.id),
                "content": "Malicious probe",
            },
            content_type="application/json",
            HTTP_X_PROFILE_ID=str(self.alice_profile_1.id),
        )
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_session_returns_404(self):
        response = self.alice.post(
            "/api/v1/chat/",
            {
                "session_id": "00000000-0000-0000-0000-000000000000",
                "content": "Unknown session",
            },
            content_type="application/json",
            HTTP_X_PROFILE_ID=str(self.alice_profile_1.id),
        )
        self.assertEqual(response.status_code, 404)

    def test_execution_trace_isolation(self):
        """Execution traces are scoped to profile."""
        from apps.agents.models import AgentExecutionLog
        log = AgentExecutionLog.objects.create(
            request_id="req-trace-123",
            profile=self.alice_profile_1,
            model_provider="mock",
            model_name="mock-model",
            prompt_version="agent:v1",
            intent_category="qa",
            iterations=1,
            outcome="success",
        )
        # Alice on profile 1 can view trace
        res1 = self.alice.get(
            "/api/v1/executions/req-trace-123/",
            HTTP_X_PROFILE_ID=str(self.alice_profile_1.id),
        )
        self.assertEqual(res1.status_code, 200)

        # Alice on profile 2 gets 404 due to profile isolation
        res2 = self.alice.get(
            "/api/v1/executions/req-trace-123/",
            HTTP_X_PROFILE_ID=str(self.alice_profile_2.id),
        )
        self.assertEqual(res2.status_code, 404)

        # Bob gets 404
        res3 = self.bob.get(
            "/api/v1/executions/req-trace-123/",
            HTTP_X_PROFILE_ID=str(self.bob_profile.id),
        )
        self.assertEqual(res3.status_code, 404)
