from django.test import SimpleTestCase, TestCase, override_settings

from shared.idempotency.keys import (
    embedding_key,
    enrichment_key,
    ocr_key,
    question_generation_key,
)


class IdempotencyKeyTests(SimpleTestCase):
    def test_keys_match_architecture_examples(self):
        self.assertEqual(ocr_key("p1", "abc", "v1"), "ocr:p1:abc:v1")
        self.assertEqual(embedding_key("c1", "abc", "qwen3-embedding:0.6b@1"), "embedding:c1:abc:qwen3-embedding:0.6b@1")
        self.assertEqual(enrichment_key("r1", "v3", "gpt-x"), "enrichment:r1:v3:gpt-x")
        self.assertEqual(question_generation_key("r1", "v2"), "question_generation:r1:v2")


class RLSContextTests(TestCase):
    def test_set_profile_context_binds_transaction_local_guc(self):
        from django.db import connection

        if connection.vendor != "postgresql":
            self.skipTest("RLS context requires PostgreSQL")
        from shared.database.rls import profile_scoped_transaction

        with profile_scoped_transaction("11111111-1111-1111-1111-111111111111"):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.current_profile_id', true)")
                value = cursor.fetchone()[0]
        self.assertEqual(value, "11111111-1111-1111-1111-111111111111")

try:
    from django.test import TransactionTestCase

    class RLSContextLeakIntegrationTests(TransactionTestCase):
        def test_context_does_not_leak_after_commit(self):
            from django.db import connection

            if connection.vendor != "postgresql":
                self.skipTest("RLS context requires PostgreSQL")
            from shared.database.rls import profile_scoped_transaction

            with profile_scoped_transaction("22222222-2222-2222-2222-222222222222"):
                pass
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.current_profile_id', true)")
                value = cursor.fetchone()[0]
            self.assertIn(value, ("", None))
except ImportError:
    pass


class JobModelTests(TestCase):
    def test_claim_is_atomic_single_winner(self):
        from apps.jobs.models import Job

        job = Job.objects.create(
            job_type="ocr",
            resource_type="document_page_revision",
            resource_id="r1",
            idempotency_key="ocr:r1:h:v1",
        )
        self.assertTrue(job.claim())
        reloaded = Job.objects.get(pk=job.pk)
        self.assertFalse(reloaded.claim(), "second claim must lose")
        self.assertEqual(reloaded.attempt_count, 1)


class ProfileAuthorizationFallbackTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.profiles.models import Profile

        User = get_user_model()
        self.user = User.objects.create_user(email="testuser@example.com", password="password123")
        self.profile1 = Profile.objects.create(user=self.user, name="Profile 1")

    def test_missing_header_returns_none_when_fallback_disabled(self):
        """When ALLOW_SINGLE_PROFILE_FALLBACK is False, missing profile header fails closed (returns None)."""
        from shared.authorization.services import ProfileAuthorizationService
        from shared.exceptions import Forbidden
        from django.test.client import RequestFactory

        rf = RequestFactory()
        request = rf.get("/api/v1/enrichment/test/")
        request.user = self.user

        with override_settings(ALLOW_SINGLE_PROFILE_FALLBACK=False):
            active = ProfileAuthorizationService.get_active_profile(request)
            self.assertIsNone(active)

            with self.assertRaises(Forbidden):
                ProfileAuthorizationService.require_active_profile(request)

    def test_single_profile_fallback_succeeds_when_enabled(self):
        """When ALLOW_SINGLE_PROFILE_FALLBACK is True, a user with 1 profile falls back successfully."""
        from shared.authorization.services import ProfileAuthorizationService
        from django.test.client import RequestFactory

        rf = RequestFactory()
        request = rf.get("/api/v1/enrichment/test/")
        request.user = self.user

        with override_settings(ALLOW_SINGLE_PROFILE_FALLBACK=True):
            active = ProfileAuthorizationService.get_active_profile(request)
            self.assertIsNotNone(active)
            self.assertEqual(active.id, self.profile1.id)

    def test_fallback_fails_closed_when_user_has_multiple_profiles(self):
        """Even with fallback enabled, a user with multiple profiles cannot be guessed (fails closed)."""
        from apps.profiles.models import Profile
        from shared.authorization.services import ProfileAuthorizationService
        from django.test.client import RequestFactory

        Profile.objects.create(user=self.user, name="Profile 2")
        rf = RequestFactory()
        request = rf.get("/api/v1/enrichment/test/")
        request.user = self.user

        with override_settings(ALLOW_SINGLE_PROFILE_FALLBACK=True):
            active = ProfileAuthorizationService.get_active_profile(request)
            self.assertIsNone(active)

    def test_explicit_header_always_resolves(self):
        """Explicit X-Active-Profile header resolves regardless of fallback setting."""
        from shared.authorization.services import ProfileAuthorizationService
        from django.test.client import RequestFactory

        rf = RequestFactory()
        request = rf.get("/api/v1/enrichment/test/", HTTP_X_ACTIVE_PROFILE=str(self.profile1.id))
        request.user = self.user

        with override_settings(ALLOW_SINGLE_PROFILE_FALLBACK=False):
            active = ProfileAuthorizationService.get_active_profile(request)
            self.assertEqual(active.id, self.profile1.id)
