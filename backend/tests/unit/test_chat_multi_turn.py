"""Phase 10D: Chat Multi-Turn Context regression test suite.

Tests regression scenarios:
- Test A: Direct continuation ("yes")
- Test B: Contextual follow-up ("Why does it help with overfitting?")
- Test C: Three-turn conversation ("Explain CNNs" -> "What does the filter mean?" -> "Can you give an example?")
- Test D: Separate chats isolation
- Test E: Profile isolation
- Test F: Reload persistence
"""
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.chat.models import ChatMessage, ChatSession
from apps.chat.services import ChatService
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from providers.llm.mock import MockLLMProvider

User = get_user_model()


class ChatMultiTurnContextRegressionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create_user(
            email="user_a@studyai.test", password="password123", first_name="UserA"
        )
        self.profile_a = Profile.objects.create(user=self.user_a, name="User A Profile", module=Profile.Module.AI_CLASSROOM)
        self.subject_a = Subject.objects.create(profile=self.profile_a, name="Computer Science")

        self.user_b = User.objects.create_user(
            email="user_b@studyai.test", password="password123", first_name="UserB"
        )
        self.profile_b = Profile.objects.create(user=self.user_b, name="User B Profile", module=Profile.Module.AI_CLASSROOM)

    def test_a_direct_continuation(self):
        """Test A — Direct continuation:

        User: "What is backpropagation?"
        Assistant: [response offering deeper dive]
        User: "yes"

        Expected:
        The second LLM call contains the previous user and assistant messages.
        The second response references the previous conversation rather than treating 'yes' as standalone.
        """
        session = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Backprop Chat"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Turn 1
            msg1 = ChatService.ask(session, "What is backpropagation?")
            self.assertEqual(mock_llm.generate_structured.call_count, 1)

            # Turn 2: User says "yes"
            msg2 = ChatService.ask(session, "yes")
            self.assertEqual(mock_llm.generate_structured.call_count, 2)

            # Inspect the second LLM call prompt
            second_call_prompt = mock_llm.generate_structured.call_args_list[1][1]["prompt"]

            # 1. Structured messages verification
            prompt_msgs = getattr(second_call_prompt, "messages", [])
            self.assertGreaterEqual(len(prompt_msgs), 2, "Second LLM call must contain multi-turn messages")
            roles = [m.get("role") for m in prompt_msgs]
            contents = [m.get("content") for m in prompt_msgs]

            self.assertIn("user", roles)
            self.assertIn("assistant", roles)
            self.assertTrue(any("What is backpropagation?" in str(c) for c in contents))
            self.assertTrue(any("yes" in str(c) for c in contents))

            # 2. Text fallback verification
            self.assertIn("What is backpropagation?", second_call_prompt.user)
            self.assertIn("yes", second_call_prompt.user)

            # 3. Response continuation verification
            self.assertNotIn("could not find anything", msg2.content.lower())
            self.assertIn("backpropagation", msg2.content.lower())

    def test_b_contextual_follow_up(self):
        """Test B — Contextual follow-up:

        User: "Explain dropout."
        User: "Why does it help with overfitting?"

        Expected:
        The second LLM call contains both turns.
        """
        session = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Dropout Chat"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Turn 1
            ChatService.ask(session, "Explain dropout.")

            # Turn 2
            msg2 = ChatService.ask(session, "Why does it help with overfitting?")

            second_call_prompt = mock_llm.generate_structured.call_args_list[1][1]["prompt"]
            prompt_msgs = getattr(second_call_prompt, "messages", [])
            contents = [str(m.get("content")) for m in prompt_msgs]

            # Assert both turns exist
            self.assertTrue(any("Explain dropout." in c for c in contents))
            self.assertTrue(any("Why does it help with overfitting?" in c for c in contents))
            self.assertIn("dropout", msg2.content.lower())
            self.assertIn("overfitting", msg2.content.lower())

    def test_c_three_turn_conversation(self):
        """Test C — Three-turn conversation:

        User: "Explain CNNs."
        User: "What does the filter mean?"
        User: "Can you give an example?"

        Expected:
        All relevant previous turns are available to the third request.
        """
        session = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="CNN Chat"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Turn 1
            ChatService.ask(session, "Explain CNNs.")
            # Turn 2
            ChatService.ask(session, "What does the filter mean?")
            # Turn 3
            msg3 = ChatService.ask(session, "Can you give an example?")

            self.assertEqual(mock_llm.generate_structured.call_count, 3)

            third_call_prompt = mock_llm.generate_structured.call_args_list[2][1]["prompt"]
            prompt_msgs = getattr(third_call_prompt, "messages", [])
            contents = [str(m.get("content")) for m in prompt_msgs]

            # All relevant previous turns must be present in the third call
            self.assertTrue(any("Explain CNNs." in c for c in contents), "Turn 1 missing from call 3")
            self.assertTrue(any("What does the filter mean?" in c for c in contents), "Turn 2 missing from call 3")
            self.assertTrue(any("Can you give an example?" in c for c in contents), "Turn 3 missing from call 3")
            self.assertIn("example", msg3.content.lower())

    def test_d_separate_chats_isolation(self):
        """Test D — Separate chats:

        Chat A: User asks about CNNs.
        Chat B: User asks about databases.
        Send another message to Chat A.

        Expected:
        Chat B messages are NOT included in Chat A context.
        """
        session_a = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Chat A CNNs"
        )
        session_b = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Chat B Databases"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Message in Chat A
            ChatService.ask(session_a, "Explain CNN architectures.")
            # Message in Chat B
            ChatService.ask(session_b, "Explain relational database indexing.")

            # Second message in Chat A
            ChatService.ask(session_a, "Can you give an example?")

            # The 3rd call is for Chat A
            third_call_prompt = mock_llm.generate_structured.call_args_list[2][1]["prompt"]
            prompt_msgs = getattr(third_call_prompt, "messages", [])
            all_text = " ".join(str(m.get("content")) for m in prompt_msgs) + third_call_prompt.user

            # Chat A must contain CNNs, and must NOT contain database indexing
            self.assertIn("CNN", all_text)
            self.assertNotIn("database indexing", all_text)
            self.assertNotIn("relational", all_text)

    def test_e_profile_isolation(self):
        """Test E — Profile isolation:

        Profile A: Conversation contains private/user-specific context.
        Profile B: Same chat endpoint must not retrieve Profile A's messages.
        """
        session_a = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Profile A Private"
        )
        ChatMessage.objects.create(
            session=session_a,
            role=ChatMessage.Role.USER,
            content="My private secret key is SECRET_ALPHA_99",
        )
        ChatMessage.objects.create(
            session=session_a,
            role=ChatMessage.Role.ASSISTANT,
            content="I noted your private secret key SECRET_ALPHA_99.",
        )

        # Profile B tries to access session_a via endpoint
        self.client.force_authenticate(user=self.user_b)
        res = self.client.get(f"/api/v1/chat/sessions/{session_a.id}/messages/")
        self.assertEqual(res.status_code, 404, "Profile B must not be able to retrieve Profile A's session")

        # Profile B creates its own session and sends a message
        session_b = ChatSession.objects.create(
            profile=self.profile_b, title="Profile B Public"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            ChatService.ask(session_b, "What is my private secret key?")
            call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            all_text = " ".join(str(m.get("content")) for m in getattr(call_prompt, "messages", [])) + call_prompt.user

            self.assertNotIn("SECRET_ALPHA_99", all_text, "Profile A's private data must never leak to Profile B")

    def test_f_reload_persistence(self):
        """Test F — Reload persistence:

        Send two or more messages.
        Refresh / query database afresh (simulating page reload).
        Continue conversation.

        Expected:
        The next message still has access to the previous conversation.
        All messages are persisted in chronological order.
        """
        session = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Reload Test Chat"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Send Turn 1
            ChatService.ask(session, "Explain backpropagation.")
            # Send Turn 2
            ChatService.ask(session, "yes")

            # Simulate reload: reload session from DB and verify persisted messages count
            reloaded_session = ChatSession.objects.get(pk=session.pk)
            persisted_msgs = list(reloaded_session.messages.order_by("created_at"))
            self.assertEqual(len(persisted_msgs), 4)
            self.assertEqual(persisted_msgs[0].role, "user")
            self.assertEqual(persisted_msgs[0].content, "Explain backpropagation.")
            self.assertEqual(persisted_msgs[1].role, "assistant")
            self.assertEqual(persisted_msgs[2].role, "user")
            self.assertEqual(persisted_msgs[2].content, "yes")
            self.assertEqual(persisted_msgs[3].role, "assistant")

            # Continue conversation after reload
            msg3 = ChatService.ask(reloaded_session, "Can you provide more details?")

            # Third call to LLM must have full history from turns 1 and 2
            third_call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            prompt_msgs = getattr(third_call_prompt, "messages", [])
            contents = [str(m.get("content")) for m in prompt_msgs]

            self.assertTrue(any("Explain backpropagation." in c for c in contents))
            self.assertTrue(any("yes" in c for c in contents))
            self.assertTrue(any("Can you provide more details?" in c for c in contents))

            # Database should now have 6 messages
            final_msgs = list(reloaded_session.messages.order_by("created_at"))
            self.assertEqual(len(final_msgs), 6)

    def test_streaming_multi_turn_context(self):
        """Verify that ChatService.stream also preserves multi-turn context end-to-end."""
        session = ChatSession.objects.create(
            profile=self.profile_a, subject=self.subject_a, title="Stream Test Chat"
        )

        with patch("apps.chat.langgraph_nodes.get_llm_provider") as mock_get_llm, \
             patch("apps.chat.langgraph_nodes.log_llm_call"):
            mock_llm = MagicMock(wraps=MockLLMProvider())
            mock_get_llm.return_value = mock_llm

            # Turn 1 streaming
            events_1 = list(ChatService.stream(session, "Explain backpropagation."))
            self.assertTrue(any(e.startswith("event: done") for e in events_1))

            # Turn 2 streaming
            events_2 = list(ChatService.stream(session, "yes"))
            self.assertTrue(any(e.startswith("event: done") for e in events_2))

            # Verify prompt for second stream
            second_call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
            prompt_msgs = getattr(second_call_prompt, "messages", [])
            contents = [str(m.get("content")) for m in prompt_msgs]

            self.assertTrue(any("Explain backpropagation." in c for c in contents))
            self.assertTrue(any("yes" in c for c in contents))
