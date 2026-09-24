"""Tests for duplicate name prevention across Profiles, Subjects, Folders, and Notes.

Ensures that duplicates (including trimmed whitespace and case-insensitive variations)
are rejected with friendly validation error messages across both create and update operations.
"""
from django.test import TestCase, override_settings
from rest_framework import status

from apps.accounts.models import User
from apps.documents.models import Document
from apps.documents.services import IngestionService
from apps.notebooks.models import Notebook
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from tests.api.utils import authenticated_client


@override_settings(STORAGE_BACKEND="local")
class DuplicateNameValidationTests(TestCase):
    def setUp(self):
        self.client = authenticated_client("student_dup@example.com", "s3curePass!x")
        self.user = User.objects.get(email="student_dup@example.com")
        self.profile = Profile.objects.get(user=self.user)

    # --- 1. Profiles Duplicate Name Tests ---

    def test_cannot_create_duplicate_profile_name_in_same_module(self):
        # Default profile already exists
        resp = self.client.post(
            "/api/v1/profiles",
            {"name": "default", "module": self.profile.module},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already have a profile with this name", str(resp.json()))

    def test_cannot_create_blank_profile_name(self):
        resp = self.client.post(
            "/api/v1/profiles",
            {"name": "   ", "module": self.profile.module},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_cannot_rename_profile_to_duplicate_name(self):
        p2 = Profile.objects.create(
            user=self.user,
            name="Semester 2",
            module=self.profile.module,
        )
        resp = self.client.patch(
            f"/api/v1/profiles/{p2.id}",
            {"name": "Default"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already have a profile with this name", str(resp.json()))

    def test_can_rename_profile_to_same_name(self):
        resp = self.client.patch(
            f"/api/v1/profiles/{self.profile.id}",
            {"name": "Default"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    # --- 2. Subjects Duplicate Name Tests ---

    def test_cannot_create_duplicate_subject_in_same_profile(self):
        Subject.objects.create(profile=self.profile, name="Physics")
        resp = self.client.post(
            "/api/v1/subjects",
            {"profile": str(self.profile.id), "name": "  physics  "},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already have a subject called", str(resp.json()))

    def test_cannot_rename_subject_to_duplicate_name(self):
        s1 = Subject.objects.create(profile=self.profile, name="Physics")
        s2 = Subject.objects.create(profile=self.profile, name="Chemistry")
        resp = self.client.patch(
            f"/api/v1/subjects/{s2.id}",
            {"name": "physics"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already have a subject called", str(resp.json()))

    def test_can_rename_subject_to_same_name(self):
        s1 = Subject.objects.create(profile=self.profile, name="Physics")
        resp = self.client.patch(
            f"/api/v1/subjects/{s1.id}",
            {"name": "Physics"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    # --- 3. Folders / Notebooks Duplicate Name Tests ---

    def test_cannot_create_duplicate_folder_in_same_subject(self):
        subject = Subject.objects.create(profile=self.profile, name="Math")
        Notebook.objects.create(profile=self.profile, subject=subject, title="Calculus")
        resp = self.client.post(
            "/api/v1/notebooks",
            {
                "profile": str(self.profile.id),
                "subject": str(subject.id),
                "title": "  calculus  ",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already exists in this subject", str(resp.json()))

    def test_cannot_rename_folder_to_duplicate_name(self):
        subject = Subject.objects.create(profile=self.profile, name="Math")
        nb1 = Notebook.objects.create(profile=self.profile, subject=subject, title="Calculus")
        nb2 = Notebook.objects.create(profile=self.profile, subject=subject, title="Algebra")
        resp = self.client.patch(
            f"/api/v1/notebooks/{nb2.id}",
            {"title": "calculus"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already exists in this subject", str(resp.json()))

    def test_can_rename_folder_to_same_name(self):
        subject = Subject.objects.create(profile=self.profile, name="Math")
        nb1 = Notebook.objects.create(profile=self.profile, subject=subject, title="Calculus")
        resp = self.client.patch(
            f"/api/v1/notebooks/{nb1.id}",
            {"title": "Calculus"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    # --- 4. Notes / Documents Duplicate Name Tests ---

    def test_cannot_create_duplicate_note_in_same_folder(self):
        subject = Subject.objects.create(profile=self.profile, name="CS")
        nb = Notebook.objects.create(profile=self.profile, subject=subject, title="Lectures")
        IngestionService.create_document(
            self.user,
            profile=self.profile,
            subject=subject,
            notebook=nb,
            title="Lecture 1",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        resp = self.client.post(
            "/api/v1/documents",
            {
                "profile": str(self.profile.id),
                "subject": str(subject.id),
                "notebook": str(nb.id),
                "title": "  lecture 1  ",
                "source_type": "image",
                "filename": "scan.png",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already exists in this folder", str(resp.json()))

    def test_cannot_rename_note_to_duplicate_in_same_folder(self):
        subject = Subject.objects.create(profile=self.profile, name="CS")
        nb = Notebook.objects.create(profile=self.profile, subject=subject, title="Lectures")
        doc1, _ = IngestionService.create_document(
            self.user,
            profile=self.profile,
            subject=subject,
            notebook=nb,
            title="Lecture 1",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        doc2, _ = IngestionService.create_document(
            self.user,
            profile=self.profile,
            subject=subject,
            notebook=nb,
            title="Lecture 2",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        resp = self.client.patch(
            f"/api/v1/documents/{doc2.id}",
            {"title": "lecture 1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already exists in this folder", str(resp.json()))

    def test_cannot_move_note_to_folder_with_colliding_title(self):
        subject = Subject.objects.create(profile=self.profile, name="CS")
        nb1 = Notebook.objects.create(profile=self.profile, subject=subject, title="Lectures")
        nb2 = Notebook.objects.create(profile=self.profile, subject=subject, title="Archive")
        doc1, _ = IngestionService.create_document(
            self.user,
            profile=self.profile,
            subject=subject,
            notebook=nb1,
            title="Overview",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        doc2, _ = IngestionService.create_document(
            self.user,
            profile=self.profile,
            subject=subject,
            notebook=nb2,
            title="Overview",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        # Attempt to move doc1 into nb2 where doc2 already exists with the same title
        resp = self.client.patch(
            f"/api/v1/documents/{doc1.id}",
            {"notebook": str(nb2.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("already exists in this folder", str(resp.json()))

    def test_same_note_title_allowed_in_different_folders(self):
        subject = Subject.objects.create(profile=self.profile, name="CS")
        nb1 = Notebook.objects.create(profile=self.profile, subject=subject, title="Lectures")
        nb2 = Notebook.objects.create(profile=self.profile, subject=subject, title="Archive")
        IngestionService.create_document(
            self.user,
            profile=self.profile,
            subject=subject,
            notebook=nb1,
            title="Introduction",
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        resp = self.client.post(
            "/api/v1/documents",
            {
                "profile": str(self.profile.id),
                "subject": str(subject.id),
                "notebook": str(nb2.id),
                "title": "Introduction",
                "source_type": "image",
                "filename": "scan.png",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
