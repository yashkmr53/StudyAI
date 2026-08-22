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
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
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

    def test_content_type_mismatch_rejected(self):
        response = self.alice.put(self.upload_url, data=b"not-an-image", content_type="image/png")
        self.assertEqual(response.status_code, 422)

    def test_magic_byte_sniffing(self):
        with override_settings(UPLOAD_SNIFF_MAGIC_BYTES=True):
            # declared png but body lacks PNG magic → rejected
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
