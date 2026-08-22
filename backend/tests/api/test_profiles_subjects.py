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
