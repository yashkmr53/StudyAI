"""Phase 12: Security & Integrity Hardening Regression Test Suite.

Verifies:
1. Global ReferenceDocument deletion authorization (non-staff 403 vs staff 204)
2. Private ReferenceDocument profile ownership and cross-profile deletion rejection
3. Backend sole-profile deletion guard (400 when 1 profile, 204 when >= 2 profiles)
4. Active profile propagation and elimination of .first() ambiguity
5. Profile isolation across Subjects, Documents, Retrieval, and References
6. PostgreSQL RLS defense-in-depth isolation
"""
import uuid
from django.test import TestCase
from django.db import connection

from apps.accounts.models import User
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.documents.models import Document
from apps.references.models import ReferenceDocument, ReferenceChunk
from apps.retrieval.models import NoteChunk
from apps.retrieval.retrieval import RetrievalService
from apps.references.services import retrieve_reference_context
from shared.database.rls import profile_scoped_transaction
from tests.api.utils import authenticated_client


class Phase12GlobalReferenceSecurityTests(TestCase):
    def setUp(self):
        # Create normal user and staff user
        self.normal_client = authenticated_client("student@example.com", "SecretPass123!")
        self.normal_user = User.objects.get(email="student@example.com")
        self.normal_profile = Profile.objects.get(user=self.normal_user)

        self.staff_client = authenticated_client("admin@example.com", "AdminPass123!")
        self.staff_user = User.objects.get(email="admin@example.com")
        self.staff_user.is_staff = True
        self.staff_user.save()
        self.staff_profile = Profile.objects.get(user=self.staff_user)

        # Create global reference (profile=None)
        self.global_ref = ReferenceDocument.objects.create(
            title="Standard Global Textbook",
            source_type=ReferenceDocument.SourceType.TEXTBOOK,
            profile=None,
            status=ReferenceDocument.Status.READY,
        )

        # Create private reference for normal user
        self.private_ref_normal = ReferenceDocument.objects.create(
            title="Student Personal Reference",
            source_type=ReferenceDocument.SourceType.REFERENCE_PDF,
            profile=self.normal_profile,
            status=ReferenceDocument.Status.READY,
        )

    def test_non_staff_cannot_delete_global_reference(self):
        """Normal user attempting to delete global reference receives 403 Forbidden."""
        response = self.normal_client.delete(
            f"/api/v1/references/{self.global_ref.id}/",
            HTTP_X_ACTIVE_PROFILE=str(self.normal_profile.id),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ReferenceDocument.objects.filter(id=self.global_ref.id).exists())

    def test_staff_can_delete_global_reference(self):
        """Staff user can successfully delete global reference."""
        response = self.staff_client.delete(
            f"/api/v1/references/{self.global_ref.id}/",
            HTTP_X_ACTIVE_PROFILE=str(self.staff_profile.id),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ReferenceDocument.objects.filter(id=self.global_ref.id).exists())

    def test_user_can_delete_own_private_reference(self):
        """Owner can successfully delete their own private reference."""
        response = self.normal_client.delete(
            f"/api/v1/references/{self.private_ref_normal.id}/",
            HTTP_X_ACTIVE_PROFILE=str(self.normal_profile.id),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ReferenceDocument.objects.filter(id=self.private_ref_normal.id).exists())

    def test_user_cannot_delete_foreign_private_reference(self):
        """Another user cannot delete someone else's private reference."""
        other_client = authenticated_client("other@example.com", "OtherPass123!")
        other_user = User.objects.get(email="other@example.com")
        other_profile = Profile.objects.get(user=other_user)

        response = other_client.delete(
            f"/api/v1/references/{self.private_ref_normal.id}/",
            HTTP_X_ACTIVE_PROFILE=str(other_profile.id),
        )
        # get_queryset scopes to user's profiles + global, so other user receives 404 Not Found
        self.assertIn(response.status_code, (403, 404))
        self.assertTrue(ReferenceDocument.objects.filter(id=self.private_ref_normal.id).exists())


class Phase12SoleProfileGuardTests(TestCase):
    def setUp(self):
        self.client = authenticated_client("multi@example.com", "MultiPass123!")
        self.user = User.objects.get(email="multi@example.com")
        self.profile1 = Profile.objects.get(user=self.user)

    def test_delete_sole_profile_rejected_with_400(self):
        """Deleting the user's only profile is rejected with 400 Bad Request."""
        self.assertEqual(Profile.objects.filter(user=self.user).count(), 1)
        response = self.client.delete(f"/api/v1/profiles/{self.profile1.id}")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_delete_profile_allowed_when_multiple_profiles_exist(self):
        """When user has 2 profiles, deleting one succeeds and leaves the other."""
        # Create 2nd profile
        create_res = self.client.post(
            "/api/v1/profiles",
            {"name": "Profile Two", "module": "NOTE_SPACE"},
            content_type="application/json",
        )
        self.assertEqual(create_res.status_code, 201)
        profile2_id = create_res.json()["id"]
        self.assertEqual(Profile.objects.filter(user=self.user).count(), 2)

        # Delete profile 2
        del_res = self.client.delete(f"/api/v1/profiles/{profile2_id}")
        self.assertEqual(del_res.status_code, 204)
        self.assertEqual(Profile.objects.filter(user=self.user).count(), 1)
        self.assertTrue(Profile.objects.filter(id=self.profile1.id).exists())

        # Attempt to delete remaining sole profile -> rejected
        del_last_res = self.client.delete(f"/api/v1/profiles/{self.profile1.id}")
        self.assertEqual(del_last_res.status_code, 400)
        self.assertEqual(Profile.objects.filter(user=self.user).count(), 1)


class Phase12MultiProfileIsolationTests(TestCase):
    def setUp(self):
        self.client = authenticated_client("isolated@example.com", "IsolatedPass123!")
        self.user = User.objects.get(email="isolated@example.com")
        self.profile_a = Profile.objects.get(user=self.user)

        self.profile_b = Profile.objects.create(
            user=self.user,
            name="Profile B",
            module=Profile.Module.NOTE_SPACE,
        )

        # Subject and Note under Profile A
        self.subject_a = Subject.objects.create(name="Subject A", profile=self.profile_a)
        self.doc_a = Document.objects.create(
            title="Note A", profile=self.profile_a, subject=self.subject_a
        )
        self.chunk_a = NoteChunk.objects.create(
            document=self.doc_a,
            profile=self.profile_a,
            subject=self.subject_a,
            revision_id=uuid.uuid4(),
            page_start=1,
            page_end=1,
            chunk_index=0,
            content="Binary Search Trees in Data Structures A",
            stale=False,
        )

        # Subject and Note under Profile B
        self.subject_b = Subject.objects.create(name="Subject B", profile=self.profile_b)
        self.doc_b = Document.objects.create(
            title="Note B", profile=self.profile_b, subject=self.subject_b
        )
        self.chunk_b = NoteChunk.objects.create(
            document=self.doc_b,
            profile=self.profile_b,
            subject=self.subject_b,
            revision_id=uuid.uuid4(),
            page_start=1,
            page_end=1,
            chunk_index=0,
            content="Quantum Physics and Superconductivity B",
            stale=False,
        )

        # Private Reference under Profile A
        self.ref_a = ReferenceDocument.objects.create(
            title="Reference A Manual",
            profile=self.profile_a,
            status=ReferenceDocument.Status.READY,
        )
        self.ref_chunk_a = ReferenceChunk.objects.create(
            reference_document=self.ref_a,
            chunk_index=0,
            page_number=1,
            text="Algorithms and Big O Complexity Analysis",
        )

        # Private Reference under Profile B
        self.ref_b = ReferenceDocument.objects.create(
            title="Reference B Manual",
            profile=self.profile_b,
            status=ReferenceDocument.Status.READY,
        )
        self.ref_chunk_b = ReferenceChunk.objects.create(
            reference_document=self.ref_b,
            chunk_index=0,
            page_number=1,
            text="Relativity and Spacetime Curvature Mechanics",
        )

        # Global Reference
        self.ref_global = ReferenceDocument.objects.create(
            title="Global Math Handbook",
            profile=None,
            status=ReferenceDocument.Status.READY,
        )
        self.ref_chunk_global = ReferenceChunk.objects.create(
            reference_document=self.ref_global,
            chunk_index=0,
            page_number=1,
            text="Linear Algebra and Matrix Calculus Operations",
        )

    def test_direct_uuid_access_blocked_across_profiles(self):
        """Active Profile A cannot access Subject B or Document B by direct UUID."""
        # Access Subject B with Profile A header
        res = self.client.get(
            f"/api/v1/subjects/{self.subject_b.id}",
            HTTP_X_ACTIVE_PROFILE=str(self.profile_a.id),
        )
        self.assertIn(res.status_code, (403, 404))

        # Access Document B with Profile A header
        res_doc = self.client.get(
            f"/api/v1/documents/{self.doc_b.id}",
            HTTP_X_ACTIVE_PROFILE=str(self.profile_a.id),
        )
        self.assertIn(res_doc.status_code, (403, 404))

    def test_retrieval_service_strictly_isolates_by_profile(self):
        """RetrievalService with Profile A returns only Note A, never Note B."""
        results_a = RetrievalService.search(
            self.user,
            "Binary Search Trees Quantum Physics",
            profile=self.profile_a,
            include_reference=False,
        )
        doc_ids_a = [str(r.document_id) for r in results_a]
        self.assertIn(str(self.doc_a.id), doc_ids_a)
        self.assertNotIn(str(self.doc_b.id), doc_ids_a)

        results_b = RetrievalService.search(
            self.user,
            "Binary Search Trees Quantum Physics",
            profile=self.profile_b,
            include_reference=False,
        )
        doc_ids_b = [str(r.document_id) for r in results_b]
        self.assertIn(str(self.doc_b.id), doc_ids_b)
        self.assertNotIn(str(self.doc_a.id), doc_ids_b)

    def test_reference_retrieval_isolates_private_and_shares_global(self):
        """Reference retrieval with Profile A returns Reference A + Global, never Reference B."""
        res_a = retrieve_reference_context(
            "Algorithms Relativity Linear Algebra",
            profile=self.profile_a,
        )
        doc_ids_a = [r["document_id"] for r in res_a]
        self.assertIn(str(self.ref_a.id), doc_ids_a)
        self.assertIn(str(self.ref_global.id), doc_ids_a)
        self.assertNotIn(str(self.ref_b.id), doc_ids_a)

        res_b = retrieve_reference_context(
            "Algorithms Relativity Linear Algebra",
            profile=self.profile_b,
        )
        doc_ids_b = [r["document_id"] for r in res_b]
        self.assertIn(str(self.ref_b.id), doc_ids_b)
        self.assertIn(str(self.ref_global.id), doc_ids_b)
        self.assertNotIn(str(self.ref_a.id), doc_ids_b)

    def test_multi_profile_search_without_profile_raises_error(self):
        """Calling RetrievalService.search without profile on multi-profile user raises ValueError."""
        with self.assertRaises(ValueError):
            RetrievalService.search(self.user, "Algorithms")


class Phase12PostgresRLSTests(TestCase):
    def test_rls_enforcement_under_profile_context(self):
        """In PostgreSQL, profile_scoped_transaction binds app.current_profile_id and clears it."""
        if connection.vendor != "postgresql":
            self.skipTest("RLS transaction binding requires PostgreSQL")

        test_profile_id = str(uuid.uuid4())
        with profile_scoped_transaction(test_profile_id):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.current_profile_id', true)")
                bound = cursor.fetchone()[0]
                self.assertEqual(bound, test_profile_id)

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_profile_id', true)")
            after = cursor.fetchone()[0]
            self.assertIn(after, ("", None))
