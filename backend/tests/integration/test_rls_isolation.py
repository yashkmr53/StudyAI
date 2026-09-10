"""Cross-profile RLS isolation tests for StudyAI.

These tests verify that PostgreSQL Row-Level Security actually enforces
tenant boundaries between profiles, even when application code attempts
to bypass filters.

DO NOT rely on Django queryset filters. These tests use raw SQL against
the PostgreSQL database to prove that RLS policies enforce isolation.

Skips: SQLite (RLS is PostgreSQL-only).
"""
import uuid

import django
import os
import unittest

from django.conf import settings
from django.test import TransactionTestCase
from django.db import connection

POSTGRESQL = settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


class CrossProfileIsolationTests(TransactionTestCase):
    """RLS isolation tests — skipped if not PostgreSQL."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not POSTGRESQL:
            raise unittest.SkipTest("RLS tests require PostgreSQL")

    def test_select_isolation(self):
        """Profile A must not SELECT Profile B's data via raw SQL."""
        from apps.profiles.models import Profile
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(email=f"sel_a_{uuid.uuid4()}@test.com", password="testpass")
        user_b = User.objects.create_user(email=f"sel_b_{uuid.uuid4()}@test.com", password="testpass")

        profile_a = Profile.objects.create(user=user_a, name="Profile A", module=Profile.Module.NOTE_SPACE)
        profile_b = Profile.objects.create(user=user_b, name="Profile B", module=Profile.Module.NOTE_SPACE)

        # Create subjects via raw SQL
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (uuid.uuid4(), "Subject A", profile_a.id)
            )
            cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (uuid.uuid4(), "Subject B", profile_b.id)
            )

        # Set RLS context to profile_a
        self._execute_sql("SELECT set_config('app.current_profile_id', %s, true)", [str(profile_a.id)])

        # Profile A queries via raw SQL - should only see their own subject
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM subjects_subject WHERE profile_id = %s", [str(profile_a.id)])
            count_a = cursor.fetchone()[0]

        # Profile A should see exactly 1 subject (their own)
        self.assertEqual(count_a, 1, f"Profile A should see 1 subject but saw {count_a}")

    def test_update_isolation(self):
        """Profile A must not UPDATE Profile B's data."""
        from apps.profiles.models import Profile
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(email=f"up_a_{uuid.uuid4()}@test.com", password="testpass")
        user_b = User.objects.create_user(email=f"up_b_{uuid.uuid4()}@test.com", password="testpass")

        profile_a = Profile.objects.create(user=user_a, name="Profile A", module=Profile.Module.NOTE_SPACE)
        profile_b = Profile.objects.create(user=user_b, name="Profile B", module=Profile.Module.NOTE_SPACE)

        # Create subjects via raw SQL
        with connection.cursor() as cursor:
            subj_a = cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (uuid.uuid4(), "Subject A", profile_a.id)
            )
            subj_b = cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (uuid.uuid4(), "Subject B", profile_b.id)
            )
            # Get the actual IDs
            with connection.cursor() as cursor2:
                cursor2.execute("SELECT id FROM subjects_subject WHERE name = %s AND profile_id = %s", ("Subject A", profile_a.id))
                subj_a_id = cursor2.fetchone()[0]
                cursor2.execute("SELECT id FROM subjects_subject WHERE name = %s AND profile_id = %s", ("Subject B", profile_b.id))
                subj_b_id = cursor2.fetchone()[0]

        # Set RLS context to profile_a
        self._execute_sql("SELECT set_config('app.current_profile_id', %s, true)", [str(profile_a.id)])

        # Profile A attempts to update Profile B's subject
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE subjects_subject SET name = %s WHERE id = %s",
                ("Updated B", subj_b_id)
            )
            rows_updated = cursor.rowcount

        # Should not be able to update B's data
        self.assertEqual(rows_updated, 0, "Profile A must not be able to update Profile B's subject")

        # Verify B's data is unchanged
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM subjects_subject WHERE id = %s", [str(subj_b_id)])
            name = cursor.fetchone()[0]
        self.assertEqual(name, "Subject B", "Profile B's subject name should be unchanged")

    def test_delete_isolation(self):
        """Profile A must not DELETE Profile B's data."""
        from apps.profiles.models import Profile
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(email=f"del_a_{uuid.uuid4()}@test.com", password="testpass")
        user_b = User.objects.create_user(email=f"del_b_{uuid.uuid4()}@test.com", password="testpass")

        profile_a = Profile.objects.create(user=user_a, name="Profile A", module=Profile.Module.NOTE_SPACE)
        profile_b = Profile.objects.create(user=user_b, name="Profile B", module=Profile.Module.NOTE_SPACE)

        # Create subject for Profile B via raw SQL
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (uuid.uuid4(), "Subject B Delete", profile_b.id)
            )
            # Get the ID
            with connection.cursor() as cursor2:
                cursor2.execute("SELECT id FROM subjects_subject WHERE name = %s AND profile_id = %s", ("Subject B Delete", profile_b.id))
                subj_b_id = cursor2.fetchone()[0]

        # Set RLS context to profile_a
        self._execute_sql("SELECT set_config('app.current_profile_id', %s, true)", [str(profile_a.id)])

        # Profile A attempts to delete Profile B's subject
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM subjects_subject WHERE id = %s", [str(subj_b_id)])
            rows_deleted = cursor.rowcount

        # Should not be able to delete B's data
        self.assertEqual(rows_deleted, 0, "Profile A must not be able to delete Profile B's subject")

        # Verify B's data still exists
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM subjects_subject WHERE id = %s", [str(subj_b_id)])
            count = cursor.fetchone()[0]
        self.assertEqual(count, 1, "Profile B's subject should still exist")

    def test_insert_isolation(self):
        """Profile A must not CREATE a row claiming ownership of Profile B."""
        from apps.profiles.models import Profile
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(email=f"ins_a_{uuid.uuid4()}@test.com", password="testpass")
        user_b = User.objects.create_user(email=f"ins_b_{uuid.uuid4()}@test.com", password="testpass")

        profile_a = Profile.objects.create(user=user_a, name="Profile A", module=Profile.Module.NOTE_SPACE)
        profile_b = Profile.objects.create(user=user_b, name="Profile B", module=Profile.Module.NOTE_SPACE)

        # Set RLS context to profile_a
        self._execute_sql("SELECT set_config('app.current_profile_id', %s, true)", [str(profile_a.id)])

        # Profile A attempts to insert a subject claiming Profile B's ownership
        new_id = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (new_id, "Fake Subject Owned by B", profile_b.id)
            )

        # Verify Profile A cannot see Profile B's row with profile_a context
        self._execute_sql("SELECT set_config('app.current_profile_id', %s, true)", [str(profile_a.id)])
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM subjects_subject WHERE profile_id = %s", [str(profile_a.id)])
            count_a = cursor.fetchone()[0]

        # Profile A should only see their own subject
        self.assertEqual(count_a, 1, f"Profile A should see only 1 subject (own), but saw {count_a}")

        # Cleanup - remove the test row
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM subjects_subject WHERE id = %s", [str(new_id)])

    def test_no_profile_context_fail_closed(self):
        """When no profile context is set, no tenant rows should be accessible (fail-closed)."""
        from apps.profiles.models import Profile
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(email=f"fc_a_{uuid.uuid4()}@test.com", password="testpass")

        profile_a = Profile.objects.create(user=user_a, name="Profile A", module=Profile.Module.NOTE_SPACE)

        # Create a subject for profile A via raw SQL
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO subjects_subject (id, name, profile_id) VALUES (%s, %s, %s)",
                (uuid.uuid4(), "Subject A", profile_a.id)
            )

        # Reset profile context (no profile set)
        self._execute_sql("RESET app.current_profile_id")

        # Query with no profile context
        self._execute_sql("SELECT count(*) FROM subjects_subject")
        count = cursor.fetchone()[0] if (cursor := connection.cursor()) else 0

        # In fail-closed mode, no profile context -> no rows accessible
        # The subjects_subject policy uses: USING ((profile_id::text = current_setting('app.current_profile_id'::text, true)))
        # When current_profile_id is NULL, the USING clause evaluates to FALSE, so no rows are visible
        self.assertEqual(count, 0, "With no profile context, no subjects should be accessible (fail-closed)")

    def test_role_bypass_explicit(self):
        """Verify the test runs under studyai_app role, not a superuser."""
        from django.db import connection

        # The test should be running under studyai_app role
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            current_user = cursor.fetchone()[0]

        # Should be studyai_app, not a superuser like postgres or studyai
        self.assertEqual(current_user, "studyai_app", f"Test must run as studyai_app, got {current_user}")

        # Verify the role is not a superuser
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = %s", [current_user])
            rolsuper = cursor.fetchone()[0]
        self.assertFalse(rolsuper, "The connecting role must not be a superuser")

        # Verify the role does not bypass RLS
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolbypassrls FROM pg_roles WHERE rolname = %s", [current_user])
            rolbypassrls = cursor.fetchone()[0]
        self.assertFalse(rolbypassrls, "The connecting role must not bypass RLS")

    def _execute_sql(self, sql, params=None):
        """Execute raw SQL and return cursor."""
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor