from django.test import TestCase

from apps.accounts.models import User
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from tests.api.utils import authenticated_client


class ProfileSubjectAPITests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.bob = authenticated_client("bob@example.com", "s3curePass!x")
        self.alice_profile = Profile.objects.get(user__email="alice@example.com")

    def test_create_and_list_subject_scoped_to_profile(self):
        response = self.alice.post(
            "/api/v1/subjects",
            {"profile": str(self.alice_profile.id), "name": "Algorithms"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        listing = self.alice.get("/api/v1/subjects").json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["results"][0]["name"], "Algorithms")

    def test_cannot_create_subject_in_foreign_profile(self):
        response = self.bob.post(
            "/api/v1/subjects",
            {"profile": str(self.alice_profile.id), "name": "Algorithms"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "FORBIDDEN")

    def test_profiles_listing_is_isolated_between_users(self):
        response = self.bob.get("/api/v1/profiles")
        names = [item["name"] for item in response.json()["results"]]
        self.assertNotIn("Sem 1", names)
        self.assertEqual(names, ["Default"])

    def test_duplicate_subject_name_rejected_per_profile(self):
        payload = {"profile": str(self.alice_profile.id), "name": "ML"}
        first = self.alice.post("/api/v1/subjects", payload, content_type="application/json")
        second = self.alice.post("/api/v1/subjects", payload, content_type="application/json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 422)

    def test_subject_requires_known_profile(self):
        response = self.alice.post(
            "/api/v1/subjects",
            {"profile": "00000000-0000-0000-0000-000000000000", "name": "Ghost"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)

    def test_list_subjects_gated_by_profile_query_param(self):
        self.alice.post(
            "/api/v1/subjects",
            {"profile": str(self.alice_profile.id), "name": "Algorithms"},
            content_type="application/json",
        )
        sem2 = Profile.objects.create(
            user=User.objects.get(email="alice@example.com"), name="Sem 2"
        )
        self.alice.post(
            "/api/v1/subjects",
            {"profile": str(sem2.id), "name": "Networks"},
            content_type="application/json",
        )

        scoped = self.alice.get(
            f"/api/v1/subjects?profile={self.alice_profile.id}"
        ).json()
        self.assertEqual([s["name"] for s in scoped["results"]], ["Algorithms"])

        unscoped = self.alice.get("/api/v1/subjects").json()
        self.assertEqual(unscoped["count"], 2)

    def test_profile_gate_rejects_foreign_and_unknown_ids(self):
        bob_profile = Profile.objects.get(user__email="bob@example.com")

        # Existing but foreign-owned: Forbidden (same semantics as create).
        foreign = self.alice.get(f"/api/v1/subjects?profile={bob_profile.id}")
        self.assertEqual(foreign.status_code, 403)
        self.assertEqual(foreign.json()["error"]["code"], "FORBIDDEN")

        # Unknown id: Not Found.
        unknown = self.alice.get(
            "/api/v1/subjects?profile=00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(unknown.status_code, 404)


class ModelConstraintTests(TestCase):
    def test_profile_unique_per_user_name(self):
        from django.db import IntegrityError, transaction

        user = User.objects.create_user(email="u@example.com", password="s3curePass!x")
        Profile.objects.create(user=user, name="A")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Profile.objects.create(user=user, name="A")

    def test_subject_unique_per_profile_name(self):
        from django.db import IntegrityError, transaction

        user = User.objects.create_user(email="u2@example.com", password="s3curePass!x")
        profile = Profile.objects.create(user=user, name="A")
        Subject.objects.create(profile=profile, name="X")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subject.objects.create(profile=profile, name="X")


class ModuleIsolationTests(TestCase):
    def setUp(self):
        self.alice = authenticated_client("alice@example.com", "s3curePass!x")
        self.user = User.objects.get(email="alice@example.com")
        self.ns_profile = Profile.objects.create(user=self.user, name="NS Profile", module=Profile.Module.NOTE_SPACE)
        self.ai_profile = Profile.objects.create(user=self.user, name="AI Profile", module=Profile.Module.AI_CLASSROOM)

    def _auth_headers(self, profile_id=None, module=None):
        headers = {"HTTP_X_ACTIVE_PROFILE": str(profile_id) if profile_id else None}
        if module:
            headers["HTTP_X_ACTIVE_MODULE"] = module
        return {k: v for k, v in headers.items() if v is not None}

    def test_create_profile_sets_module_from_header(self):
        response = self.alice.post(
            "/api/v1/profiles",
            {"name": "New NS"},
            content_type="application/json",
            **self._auth_headers(module=Profile.Module.NOTE_SPACE),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["module"], Profile.Module.NOTE_SPACE)

    def test_list_profiles_filtered_by_module(self):
        response = self.alice.get(
            "/api/v1/profiles",
            **self._auth_headers(module=Profile.Module.AI_CLASSROOM),
        )
        self.assertEqual(response.status_code, 200)
        names = [p["name"] for p in response.json()["results"]]
        self.assertIn("AI Profile", names)
        self.assertNotIn("NS Profile", names)

    def test_cross_module_profile_access_rejected(self):
        response = self.alice.get(
            f"/api/v1/profiles/{self.ns_profile.id}",
            **self._auth_headers(profile_id=self.ns_profile.id, module=Profile.Module.AI_CLASSROOM),
        )
        self.assertEqual(response.status_code, 403)

    def test_cross_module_subject_access_rejected(self):
        Subject.objects.create(profile=self.ns_profile, name="NS Subject")
        response = self.alice.get(
            f"/api/v1/subjects?profile={self.ns_profile.id}",
            **self._auth_headers(profile_id=self.ns_profile.id, module=Profile.Module.AI_CLASSROOM),
        )
        self.assertEqual(response.status_code, 403)

    def test_profile_module_update_via_patch(self):
        response = self.alice.patch(
            f"/api/v1/profiles/{self.ns_profile.id}",
            {"module": Profile.Module.AI_CLASSROOM},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["module"], Profile.Module.AI_CLASSROOM)

    def test_unique_name_per_module(self):
        from django.db import IntegrityError, transaction

        Profile.objects.create(user=self.user, name="A", module=Profile.Module.NOTE_SPACE)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Profile.objects.create(user=self.user, name="A", module=Profile.Module.NOTE_SPACE)

    def test_subject_unique_per_profile_name(self):
        from django.db import IntegrityError, transaction

        user = User.objects.create_user(email="u2@example.com", password="s3curePass!x")
        profile = Profile.objects.create(user=user, name="A")
        Subject.objects.create(profile=profile, name="X")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subject.objects.create(profile=profile, name="X")
