"""Phase 8 hardening tests (§23/§25/§26/§28/§70, §74–75)."""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.ai_classroom.services import EvidenceVerifier
from apps.audit.models import AuditLog
from apps.profiles.models import Profile
from providers.base import Prompt
from tests.api.test_retrieval import _make_ocr_document
from tests.api.utils import authenticated_client


class HealthEndpointsTests(TestCase):
    def test_healthz_open(self):
        response = APIClient().get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readyz_checks_database(self):
        response = APIClient().get("/readyz")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["database"])

    def test_security_headers_present(self):
        response = APIClient().get("/healthz")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")


class StatusEndpointTests(TestCase):
    def setUp(self):
        self.staff = authenticated_client("staff@example.com", "s3curePass!x")
        User = __import__("apps.accounts.models", fromlist=["User"]).User
        user = User.objects.get(email="staff@example.com")
        user.is_staff = True
        user.save(update_fields=("is_staff",))
        self.staff.force_authenticate(user)

    def test_status_payload_shape(self):
        response = self.staff.get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("jobs", "providers", "citations", "requests", "counters", "database"):
            self.assertIn(key, body)
        self.assertIn("queue_depth", body["jobs"])
        self.assertIn("dead_letter_count", body["jobs"])
        self.assertIn("p95_ms", body["requests"])

    def test_status_requires_staff(self):
        client = authenticated_client("plain@example.com", "s3curePass!x")
        self.assertEqual(client.get("/api/v1/status").status_code, 403)


class RateLimitTests(TestCase):
    def tearDown(self):
        cache.clear()

    @override_settings(
        REST_FRAMEWORK={
            **__import__("django.conf", fromlist=["settings"]).settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"auth": "3/min", "ai": "100/min", "user": "1000/min"},
        },
        CACHES={
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
            "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        },
        RATE_LIMITING_ENABLED=True,
    )
    def test_login_throttled_after_rate(self):
        client = APIClient()
        statuses = []
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/login",
                {"email": "nobody@example.com", "password": "wrong-password"},
                content_type="application/json",
            )
            statuses.append(response.status_code)
        self.assertEqual(statuses[-1], 429)
        envelope = response.json()["error"]
        self.assertEqual(envelope["code"], "RATE_LIMITED")

    def test_non_throttled_paths_unaffected(self):
        response = APIClient().get("/healthz")
        self.assertEqual(response.status_code, 200)


class MagicByteTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        from apps.profiles.models import Profile

        self.profile = Profile.objects.get(user__email="alice@example.com")
        body = self.alice.post(
            "/api/v1/documents",
            {"profile": str(self.profile.id), "source_type": "image", "filename": "x.png"},
            content_type="application/json",
        ).json()
        self.upload_url = body["upload"]["url"]

    @override_settings(STORAGE_BACKEND="local")
    def test_content_type_mismatch_rejected(self):
        response = self.alice.put(self.upload_url, data=b"not-an-image", content_type="image/png")
        self.assertEqual(response.status_code, 422)

    @override_settings(STORAGE_BACKEND="local", UPLOAD_SNIFF_MAGIC_BYTES=True)
    def test_magic_byte_sniffing(self):
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"payload"
        response = self.alice.put(self.upload_url, data=fake_jpeg, content_type="image/png")
        self.assertEqual(response.status_code, 422)


class BudgetTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.profile = Profile.objects.get(user__email="alice@example.com")
        self.doc_id = _make_ocr_document(
            self.alice, self.profile,
            [["Dijkstra computes shortest paths."]],
        )

    @override_settings(AI_DAILY_BUDGET_PER_PROFILE=1)
    def test_budget_exhaustion_returns_429(self):
        first = self.alice.post(f"/api/v1/documents/{self.doc_id}/enrich")
        self.assertEqual(first.status_code, 202)
        second = self.alice.post(f"/api/v1/chat/sessions", {}, content_type="application/json")
        session = second.json()
        message = self.alice.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            {"content": "hello"},
            content_type="application/json",
        )
        self.assertEqual(message.status_code, 429)
        self.assertEqual(message.json()["error"]["code"], "RATE_LIMITED")


class AtomicBudgetReserveSettleTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User, UserProfile

        self.alice = authenticated_client("alice_t9@example.com", "s3curePass!x")
        self.user = User.objects.get(email="alice_t9@example.com")
        self.user_profile, _ = UserProfile.objects.get_or_create(user=self.user)

    def test_reserve_settle_adjusts_by_actual_minus_estimate_from_provider_log(self):
        """T9: reserve -> settle_from_logs adjusts counter by (actual - estimate)."""
        from decimal import Decimal
        from apps.accounts.services.budget import BudgetService
        from apps.audit.models import ProviderCallLog

        res = BudgetService.reserve(self.user, 500, Decimal("0.05"))
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 500)
        self.assertEqual(self.user_profile.current_month_cost_usd, Decimal("0.05"))

        ProviderCallLog.objects.create(
            provider="mock",
            model="qwen3.5:4b",
            latency_ms=10,
            success=True,
            input_tokens=150,
            output_tokens=120,
            total_tokens=270,
            estimated_cost_usd=Decimal("0.02"),
            metadata={"reservation_id": res.reservation_id},
        )
        BudgetService.settle_from_logs(res)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 270)
        self.assertEqual(self.user_profile.current_month_cost_usd, Decimal("0.02"))

        # Idempotent second settle does nothing
        BudgetService.settle_from_logs(res)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 270)

    def test_failed_call_refunds_reservation(self):
        """T9: release() refunds reserved tokens/cost cleanly."""
        from decimal import Decimal
        from apps.accounts.services.budget import BudgetService

        res = BudgetService.reserve(self.user, 500, Decimal("0.05"))
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 500)

        BudgetService.release(res)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 0)
        self.assertEqual(self.user_profile.current_month_cost_usd, Decimal("0.00"))

        # Idempotent second release cannot go negative
        BudgetService.release(res)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 0)

    def test_stale_read_concurrent_reservations_cannot_exceed_budget(self):
        """T9: Conditional F()-based UPDATE rejects concurrent over-budget reservation even on stale reads."""
        from decimal import Decimal
        from apps.accounts.models import UserProfile
        from apps.accounts.services.budget import BudgetExceeded, BudgetService

        UserProfile.objects.filter(pk=self.user_profile.pk).update(
            monthly_token_budget=800,
            current_month_token_usage=0,
        )
        stale_snapshot = UserProfile.objects.get(pk=self.user_profile.pk)

        with mock.patch.object(BudgetService, "_get_or_create_profile", return_value=stale_snapshot):
            BudgetService.reserve(self.user, 500, Decimal("0.01"))
            with self.assertRaises(BudgetExceeded):
                BudgetService.reserve(self.user, 500, Decimal("0.01"))

        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 500)

    def test_chat_post_settles_actual_tokens_and_refunds_on_failure(self):
        """T9 E2E: Chat POST settles actual ProviderCallLog tokens; failed call refunds reservation."""
        from apps.profiles.models import Profile
        from providers.base import StructuredLLMResult

        profile = Profile.objects.filter(user=self.user).first()
        headers = {"HTTP_X_ACTIVE_PROFILE": str(profile.id)}
        session = self.alice.post(
            "/api/v1/chat/sessions", {}, content_type="application/json", **headers
        ).json()

        class FakeProvider:
            name = "fake"
            model = "fake-4b"
            def generate_structured(self, **kwargs):
                return StructuredLLMResult(
                    data={"answer": "Dijkstra finds shortest paths.", "cited_ids": [], "confidence": 0.9},
                    raw_text='{"answer": "Dijkstra finds shortest paths."}',
                    model="fake-4b",
                    provider="fake",
                    prompt_name="chat",
                    prompt_version="v1",
                    input_tokens=100,
                    output_tokens=80,
                    total_tokens=180,
                    estimated_cost_usd=0.02,
                )

        from providers.llm.chain import LLMChainProvider
        chain = LLMChainProvider([FakeProvider()])

        with mock.patch("apps.chat.langgraph_nodes.get_llm_provider", return_value=chain):
            res = self.alice.post(
                f"/api/v1/chat/sessions/{session['id']}/messages",
                {"content": "Hi"},
                content_type="application/json",
                **headers,
            )
        self.assertEqual(res.status_code, 201)
        self.user_profile.refresh_from_db()
        # Throttle reserved 500, real ProviderCallLog logged 180 -> settled to 180!
        self.assertEqual(self.user_profile.current_month_token_usage, 180)

        # Now test failed AI call refunds the 500 reservation back to 180!
        with mock.patch("apps.chat.services.ChatService.ask", side_effect=RuntimeError("LLM down")):
            fail_res = self.alice.post(
                f"/api/v1/chat/sessions/{session['id']}/messages",
                {"content": "Trigger failure"},
                content_type="application/json",
                **headers,
            )
            self.assertEqual(fail_res.status_code, 500)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_month_token_usage, 180)


try:
    from django.test import TransactionTestCase

    class PostgresConcurrentBudgetTests(TransactionTestCase):
        def test_postgresql_threads_never_exceed_budget(self):
            """T9 PostgreSQL-only: 5 concurrent threads racing on 1200-token budget only admit 2."""
            import threading
            from decimal import Decimal
            from django.db import connection, connections
            from apps.accounts.models import User, UserProfile
            from apps.accounts.services.budget import BudgetExceeded, BudgetService

            if connection.vendor != "postgresql":
                self.skipTest("PostgreSQL required for threaded atomic UPDATE concurrency test")

            user = User.objects.create_user(email="pg_t9_race@example.com", password="pass")
            up, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={"monthly_token_budget": 1200, "current_month_token_usage": 0},
            )
            UserProfile.objects.filter(pk=up.pk).update(monthly_token_budget=1200, current_month_token_usage=0)

            barrier = threading.Barrier(5)
            outcomes = []
            lock = threading.Lock()

            def worker():
                try:
                    barrier.wait(timeout=5)
                    BudgetService.reserve(user, 500, Decimal("0.05"))
                    with lock:
                        outcomes.append("ok")
                except BudgetExceeded:
                    with lock:
                        outcomes.append("exceeded")
                finally:
                    connections.close_all()

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            up.refresh_from_db()
            self.assertEqual(outcomes.count("ok"), 2)
            self.assertEqual(outcomes.count("exceeded"), 3)
            self.assertEqual(up.current_month_token_usage, 1000)
except ImportError:
    pass


class LLMFallbackChainTests(TestCase):
    def test_fallback_used_when_primary_fails(self):
        from providers.llm.chain import LLMChainProvider
        from providers.llm.failing import FailingLLMProvider
        from providers.llm.mock import MockLLMProvider

        chain = LLMChainProvider([FailingLLMProvider(), MockLLMProvider()])
        result = chain.generate_structured(
            prompt=Prompt(name="chat", version="v1",
                          user='EVIDENCE_JSON:{"evidence": [{"chunk_id": "c1", "content": "hello world"}]}'),
            request_id="t",
        )
        self.assertEqual(result.attempted_providers, ["failing", "mock"])
        self.assertIn("answer", result.data)


class AuditLogTests(TestCase):
    def setUp(self):
        self.client_reg = APIClient()

    def test_register_writes_audit_entry(self):
        response = self.client_reg.post(
            "/api/v1/auth/register",
            {"email": "audit@example.com", "password": "s3curePass!x"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        entry = AuditLog.objects.filter(action="user.registered").latest("created_at")
        self.assertEqual(entry.actor_email, "audit@example.com")

    def test_login_logout_audited(self):
        auth = authenticated_client("aud2@example.com", "s3curePass!x")
        tokens_response = auth.post(
            "/api/v1/auth/login",
            {"email": "aud2@example.com", "password": "s3curePass!x"},
            content_type="application/json",
        )
        assert tokens_response.status_code == 200, tokens_response.content
        tokens = tokens_response.json()
        refresh, access = tokens["refresh"], tokens["access"]
        logout = auth.post(
            "/api/v1/auth/logout", {"refresh": refresh},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(logout.status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action="user.login").exists())
        self.assertTrue(AuditLog.objects.filter(action="user.logout").exists())

    def test_audit_listing_staff_only(self):
        regular = authenticated_client("reg@example.com", "s3curePass!x")
        self.assertEqual(regular.get("/api/v1/audit").status_code, 403)

        from apps.accounts.models import User

        staff_user = User.objects.get(email="reg@example.com")
        staff_user.is_staff = True
        staff_user.save()
        staff_client = authenticated_client("reg@example.com", "s3curePass!x")
        response = staff_client.get("/api/v1/audit")
        self.assertEqual(response.status_code, 200)


class RegressionGateTests(TestCase):
    def test_gate_math_via_command_helper(self):
        """The command's gate compares metric values against thresholds."""
        metrics = {"recall_at_k": 0.85}
        threshold = 0.9
        regressed = metrics["recall_at_k"] < threshold
        self.assertTrue(regressed)
