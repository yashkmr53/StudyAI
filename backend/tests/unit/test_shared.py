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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_promote_due_retries_dispatches_once_via_on_commit_and_beat_configured(self):
        """T7: Due retryable jobs are promoted, dispatched via on_commit, and not double-dispatched on 2nd pass."""
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from apps.jobs.models import Job
        from apps.jobs.services import promote_due_retries
        from config.celery import app as celery_app

        self.assertIn("promote-retries", celery_app.conf.beat_schedule)
        self.assertEqual(
            celery_app.conf.beat_schedule["promote-retries"]["task"],
            "apps.jobs.tasks.promote_retries_task",
        )

        due_job = Job.objects.create(
            job_type="ocr",
            resource_type="document_page_revision",
            resource_id="r-due",
            idempotency_key="ocr:r-due:h:v1",
            status=Job.Status.FAILED_RETRYABLE,
            next_retry_at=timezone.now() - timedelta(seconds=10),
        )
        future_job = Job.objects.create(
            job_type="ocr",
            resource_type="document_page_revision",
            resource_id="r-future",
            idempotency_key="ocr:r-future:h:v1",
            status=Job.Status.FAILED_RETRYABLE,
            next_retry_at=timezone.now() + timedelta(minutes=10),
        )

        with patch("apps.jobs.tasks.process_job_task.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                promoted = promote_due_retries()

            self.assertEqual(promoted, 1)
            due_job.refresh_from_db()
            future_job.refresh_from_db()
            self.assertEqual(due_job.status, Job.Status.QUEUED)
            self.assertEqual(future_job.status, Job.Status.FAILED_RETRYABLE)
            mock_delay.assert_called_once_with(str(due_job.pk))

            # Second promotion pass must neither re-promote nor double-dispatch
            with self.captureOnCommitCallbacks(execute=True):
                promoted_second = promote_due_retries()
            self.assertEqual(promoted_second, 0)
            self.assertEqual(mock_delay.call_count, 1)


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


class RLSMiddlewareCleanupTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.profiles.models import Profile

        User = get_user_model()
        self.user = User.objects.create_user(email="rls_mw@example.com", password="password123")
        self.profile = Profile.objects.create(user=self.user, name="MW Profile")

    def test_middleware_clears_profile_context_when_prev_empty(self):
        """T2 unit: RlsContextMiddleware must call clear_profile_context() in finally when prev is empty."""
        from unittest.mock import patch
        from django.test.client import RequestFactory
        from shared.database.middleware import RlsContextMiddleware

        rf = RequestFactory()
        request = rf.get("/api/v1/documents", HTTP_X_ACTIVE_PROFILE=str(self.profile.id))
        request.user = self.user

        mw = RlsContextMiddleware(lambda req: "ok")
        with patch("shared.database.rls.get_current_profile_id", return_value=""), \
             patch("shared.database.rls.bind_profile_session") as mock_bind, \
             patch("shared.database.rls.clear_profile_context") as mock_clear:
            resp = mw(request)

        self.assertEqual(resp, "ok")
        mock_bind.assert_called_once_with(str(self.profile.id))
        mock_clear.assert_called_once()


try:
    from django.test import TransactionTestCase

    class RLSMiddlewarePostgresLeakTests(TransactionTestCase):
        def test_unauthenticated_request_after_authenticated_sees_no_profile(self):
            """T2 PostgreSQL-only: Persistent connection does not retain app.current_profile_id across requests."""
            from django.contrib.auth import get_user_model
            from django.contrib.auth.models import AnonymousUser
            from django.db import connection
            from django.test.client import RequestFactory
            from apps.profiles.models import Profile
            from shared.database.middleware import RlsContextMiddleware
            from shared.database.rls import clear_profile_context, get_current_profile_id

            if connection.vendor != "postgresql":
                self.skipTest("PostgreSQL required for real GUC leak check")

            clear_profile_context()
            User = get_user_model()
            user = User.objects.create_user(email="rls_pg@example.com", password="password123")
            profile = Profile.objects.create(user=user, name="PG Profile")

            observed_gucs = []

            def view_fn(req):
                observed_gucs.append(get_current_profile_id())
                return "ok"

            mw = RlsContextMiddleware(view_fn)
            rf = RequestFactory()

            # Simulate persistent connection (CONN_MAX_AGE > 0) reusing same connection across requests
            with override_settings(CONN_MAX_AGE=600):
                auth_req = rf.get("/api/v1/documents", HTTP_X_ACTIVE_PROFILE=str(profile.id))
                auth_req.user = user
                mw(auth_req)

                anon_req = rf.get("/healthz")
                anon_req.user = AnonymousUser()
                mw(anon_req)

            self.assertEqual(observed_gucs[0], str(profile.id))
            self.assertEqual(observed_gucs[1], "")
            self.assertEqual(get_current_profile_id(), "")
except ImportError:
    pass
