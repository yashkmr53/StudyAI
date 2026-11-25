"""Tests for ASGI entrypoint, async middlewares, LLM astream, and async SSE streaming (R6)."""
import asyncio
import json
from decimal import Decimal
from unittest.mock import patch

import httpx
from asgiref.sync import iscoroutinefunction
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.audit.models import ProviderCallLog
from apps.chat.models import ChatMessage, ChatSession
from apps.chat.services import ChatService
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from providers.base import Prompt, StreamingLLMProvider
from providers.llm.chain import LLMChainProvider
from providers.llm.mock import MockLLMProvider

User = get_user_model()


class AsgiApplicationAndMiddlewareTests(SimpleTestCase):
    def test_asgi_application_and_async_middleware_chain(self):
        from config.asgi import application

        self.assertIsNotNone(application)
        cur = application._middleware_chain
        layers = []
        for _ in range(30):
            layers.append((getattr(cur, "__qualname__", str(type(cur))), iscoroutinefunction(cur)))
            cur = getattr(cur, "get_response", None) or getattr(cur, "__wrapped__", None)
            if cur is None:
                break

        self.assertTrue(len(layers) > 5)
        self.assertTrue(
            all(is_async for _, is_async in layers),
            f"Expected every ASGI middleware layer to be async, got: {layers}",
        )

    def test_custom_middlewares_declare_async_capability(self):
        from django.conf import settings
        from django.utils.module_loading import import_string

        custom_paths = [m for m in settings.MIDDLEWARE if m.startswith("shared.")]
        self.assertEqual(len(custom_paths), 5)
        for path in custom_paths:
            cls = import_string(path)
            self.assertTrue(getattr(cls, "sync_capable", False), f"{path} missing sync_capable=True")
            self.assertTrue(getattr(cls, "async_capable", False), f"{path} missing async_capable=True")
            self.assertTrue(hasattr(cls, "__acall__"), f"{path} missing __acall__")


class LLMProviderAstreamTests(TransactionTestCase):
    def test_llm_provider_astream_yields_tokens_and_logs(self):
        mock_provider = MockLLMProvider()
        self.assertIsInstance(mock_provider, StreamingLLMProvider)

        chain = LLMChainProvider([mock_provider])
        prompt = Prompt(name="chat", version="v1", system="Be concise.", user="Explain eigenvalues simply.")

        async def _collect():
            from asgiref.sync import sync_to_async
            from django.db import connections

            chunks = []
            try:
                async for delta in chain.astream(prompt=prompt, request_id="req-r6-1"):
                    chunks.append(delta)
                return chunks
            finally:
                await sync_to_async(connections.close_all, thread_sensitive=True)()

        chunks = asyncio.run(_collect())
        self.assertTrue(len(chunks) >= 1)
        combined = "".join(chunks).strip()
        self.assertIn("Mock response", combined)
        self.assertTrue(ProviderCallLog.objects.filter(provider="mock", success=True).exists())


class AsyncSSEStreamingTests(TransactionTestCase):
    def setUp(self):
        from shared.database.rls import bind_profile_session

        self.alice = User.objects.create_user(email="alice_r6@example.com", password="pw")
        UserProfile.objects.update_or_create(
            user=self.alice,
            defaults={
                "monthly_token_budget": 100000,
                "monthly_cost_budget_usd": Decimal("50.00"),
            },
        )
        self.profile_a = Profile.objects.create(user=self.alice, name="Alice R6", module=Profile.Module.NOTE_SPACE)
        bind_profile_session(self.profile_a.id)
        self.subject_a = Subject.objects.create(profile=self.profile_a, name="Linear Algebra")

        self.bob = User.objects.create_user(email="bob_r6@example.com", password="pw")
        self.profile_b = Profile.objects.create(user=self.bob, name="Bob R6", module=Profile.Module.NOTE_SPACE)

    def tearDown(self):
        from shared.database.rls import clear_profile_context

        clear_profile_context()

    def test_chat_service_astream_concurrent_without_blocking_sleep(self):
        s1 = ChatSession.objects.create(profile=self.profile_a, subject=self.subject_a)
        s2 = ChatSession.objects.create(profile=self.profile_a, subject=self.subject_a)

        def _forbid_sleep(_seconds):
            raise AssertionError("Blocking time.sleep must not be called inside async ChatService.astream")

        async def _consume(session, message):
            events = []
            async for raw in ChatService.astream(session, message):
                events.append(raw)
            return events

        async def _run_both():
            return await asyncio.gather(
                _consume(s1, "Hello first async stream"),
                _consume(s2, "Hello second async stream"),
            )

        with patch("apps.chat.services.time.sleep", side_effect=_forbid_sleep):
            events_1, events_2 = asyncio.run(_run_both())

        for events in (events_1, events_2):
            self.assertTrue(any(e.startswith("event: title") for e in events))
            self.assertTrue(any(e.startswith("event: token") for e in events))
            self.assertTrue(any(e.startswith("event: done") for e in events))

        self.assertEqual(ChatMessage.objects.filter(session=s1).count(), 2)
        self.assertEqual(ChatMessage.objects.filter(session=s2).count(), 2)

    def test_asgi_http_sse_stream_endpoint_with_middlewares_and_rls_isolation(self):
        from config.asgi import application

        from shared.database.rls import profile_scoped_transaction

        session_a = ChatSession.objects.create(profile=self.profile_a, subject=self.subject_a)
        with profile_scoped_transaction(self.profile_b.id):
            session_b = ChatSession.objects.create(profile=self.profile_b, title="Bob Secret Session")
        alice_token = str(RefreshToken.for_user(self.alice).access_token)
        bob_token = str(RefreshToken.for_user(self.bob).access_token)

        async def _run_http():
            from asgiref.sync import sync_to_async
            from django.db import connections

            transport = httpx.ASGITransport(app=application)
            try:
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    stream_resp, bob_denied_resp = await asyncio.gather(
                        client.post(
                            f"/api/v1/chat/sessions/{session_a.pk}/messages/stream",
                            json={"content": "Explain orthogonality cleanly"},
                            headers={
                                "Authorization": f"Bearer {alice_token}",
                                "X-Active-Profile": str(self.profile_a.pk),
                            },
                        ),
                        client.get(
                            f"/api/v1/chat/sessions/{session_a.pk}/messages",
                            headers={
                                "Authorization": f"Bearer {bob_token}",
                                "X-Active-Profile": str(self.profile_b.pk),
                            },
                        ),
                    )
                    # Ensure Bob's session isn't visible to Alice either
                    alice_denied_resp = await client.get(
                        f"/api/v1/chat/sessions/{session_b.pk}/messages",
                        headers={
                            "Authorization": f"Bearer {alice_token}",
                            "X-Active-Profile": str(self.profile_a.pk),
                        },
                    )
                    return stream_resp, bob_denied_resp, alice_denied_resp
            finally:
                await sync_to_async(connections.close_all, thread_sensitive=True)()

        stream_resp, bob_denied_resp, alice_denied_resp = asyncio.run(_run_http())

        self.assertEqual(stream_resp.status_code, 200)
        self.assertIn("text/event-stream", stream_resp.headers.get("content-type", ""))
        self.assertTrue(stream_resp.headers.get("X-Request-ID"))
        self.assertTrue(stream_resp.headers.get("X-Duration-Ms"))
        self.assertEqual(stream_resp.headers.get("X-Content-Type-Options"), "nosniff")

        body = stream_resp.text
        self.assertIn("event: token", body)
        self.assertIn("event: done", body)

        # Parse done payload and verify persisted message
        done_lines = [line for line in body.splitlines() if line.startswith("data: ")]
        done_payload = json.loads(done_lines[-1].removeprefix("data: ").strip())
        self.assertIn("message_id", done_payload)
        self.assertEqual(ChatMessage.objects.filter(session=session_a).count(), 2)

        # Cross-profile checks held under concurrent ASGI requests
        self.assertEqual(bob_denied_resp.status_code, 404)
        self.assertEqual(alice_denied_resp.status_code, 404)
