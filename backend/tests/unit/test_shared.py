from django.test import SimpleTestCase, TestCase

from shared.idempotency.keys import (
    embedding_key,
    enrichment_key,
    ocr_key,
    question_generation_key,
)


class IdempotencyKeyTests(SimpleTestCase):
    def test_keys_match_architecture_examples(self):
        self.assertEqual(ocr_key("p1", "abc", "v1"), "ocr:p1:abc:v1")
        self.assertEqual(embedding_key("c1", "abc", "bge-m3@1"), "embedding:c1:abc:bge-m3@1")
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
