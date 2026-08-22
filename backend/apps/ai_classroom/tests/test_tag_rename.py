"""Tag rename endpoint tests (B4)."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.ai_classroom.models import Tag


class TagRenameTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="alice@example.com", password="pass123")
        self.profile = Profile.objects.create(user=self.user, name="Alice")
        self.subject = Subject.objects.create(profile=self.profile, name="Mathematics")
        self.client.force_authenticate(self.user)

        # Create a tag
        self.tag = Tag.objects.create(
            subject=self.subject,
            stable_key="calculus",
            display_name="Calculus",
        )

    def test_rename_tag(self):
        """Test POST /api/v1/tags/{id}/rename/"""
        resp = self.client.post(
            f"/api/v1/tags/{self.tag.pk}/rename",
            {"name": "Differential Calculus"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["display_name"], "Differential Calculus")
        self.assertEqual(resp.data["stable_key"], "calculus")  # stable_key unchanged

    def test_rename_tag_same_name(self):
        """Test renaming to the same name returns 200 with current data."""
        resp = self.client.post(
            f"/api/v1/tags/{self.tag.pk}/rename",
            {"name": "Calculus"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["display_name"], "Calculus")

    def test_rename_tag_empty_name(self):
        """Test renaming with empty name returns 422."""
        resp = self.client.post(
            f"/api/v1/tags/{self.tag.pk}/rename",
            {"name": ""},
        )
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_rename_tag_too_long(self):
        """Test renaming with name > 120 chars returns 422."""
        long_name = "A" * 121
        resp = self.client.post(
            f"/api/v1/tags/{self.tag.pk}/rename",
            {"name": long_name},
        )
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_rename_nonexistent_tag(self):
        """Test renaming non-existent tag returns 404."""
        import uuid
        fake_id = uuid.uuid4()
        resp = self.client.post(
            f"/api/v1/tags/{fake_id}/rename",
            {"name": "New Name"},
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_rename_tag_other_user(self):
        """Test user cannot rename another user's tag."""
        other_user = User.objects.create_user(email="bob@example.com", password="pass123")
        other_profile = Profile.objects.create(user=other_user, name="Bob")
        other_subject = Subject.objects.create(profile=other_profile, name="Physics")
        other_tag = Tag.objects.create(
            subject=other_subject,
            stable_key="quantum",
            display_name="Quantum Mechanics",
        )

        resp = self.client.post(
            f"/api/v1/tags/{other_tag.pk}/rename/",
            {"name": "Hacked"},
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)