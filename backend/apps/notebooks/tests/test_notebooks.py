"""Notebooks CRUD + RLS tests (B1)."""
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.notebooks.models import Notebook, NotebookPage, NotebookLine


class NotebookCRUDTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="alice@example.com", password="pass123")
        self.profile = Profile.objects.create(user=self.user, name="Alice")
        self.subject = Subject.objects.create(profile=self.profile, name="Mathematics")
        self.client.force_authenticate(self.user)

    def test_create_notebook(self):
        resp = self.client.post(
            "/api/v1/notebooks",
            {"profile": str(self.profile.pk), "subject": str(self.subject.pk), "title": "My Notebook", "description": "Notes"},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["title"], "My Notebook")
        self.assertEqual(str(resp.data["subject"]), str(self.subject.pk))

    def test_create_notebook_without_subject(self):
        resp = self.client.post(
            "/api/v1/notebooks",
            {"profile": str(self.profile.pk), "title": "No Subject Notebook"},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(resp.data["subject"])

    def test_list_notebooks(self):
        # Create fresh notebooks for this test
        nb1 = Notebook.objects.create(profile=self.profile, subject=self.subject, title="Notebook 1")
        nb2 = Notebook.objects.create(profile=self.profile, subject=self.subject, title="Notebook 2")

        resp = self.client.get("/api/v1/notebooks")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Check that our notebooks are in the results
        result_data = resp.data.get("results", resp.data)
        result_ids = {item["id"] for item in result_data}
        self.assertIn(str(nb1.pk), result_ids)
        self.assertIn(str(nb2.pk), result_ids)

    def test_retrieve_notebook(self):
        notebook = Notebook.objects.create(profile=self.profile, subject=self.subject, title="Retrieve Me")
        resp = self.client.get(f"/api/v1/notebooks/{notebook.pk}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["title"], "Retrieve Me")

    def test_update_notebook(self):
        notebook = Notebook.objects.create(profile=self.profile, subject=self.subject, title="Old Title")
        resp = self.client.patch(
            f"/api/v1/notebooks/{notebook.pk}",
            {"title": "New Title", "description": "Updated"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["title"], "New Title")
        self.assertEqual(resp.data["description"], "Updated")

    def test_delete_notebook(self):
        notebook = Notebook.objects.create(profile=self.profile, subject=self.subject, title="To Delete")
        resp = self.client.delete(f"/api/v1/notebooks/{notebook.pk}")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notebook.objects.filter(pk=notebook.pk).exists())


class NotebookPageTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="bob@example.com", password="pass123")
        self.profile = Profile.objects.create(user=self.user, name="Bob")
        self.subject = Subject.objects.create(profile=self.profile, name="Physics")
        self.notebook = Notebook.objects.create(profile=self.profile, subject=self.subject, title="Physics Notes")
        self.client.force_authenticate(self.user)

    def test_create_page(self):
        resp = self.client.post(
            f"/api/v1/notebooks/{self.notebook.pk}/pages",
            {"notebook": str(self.notebook.pk), "page_number": 1, "canvas_state": {}},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["page_number"], 1)

    def test_list_pages(self):
        # Create fresh pages for this test
        page1 = NotebookPage.objects.create(notebook=self.notebook, page_number=1)
        page2 = NotebookPage.objects.create(notebook=self.notebook, page_number=2)

        resp = self.client.get(f"/api/v1/notebooks/{self.notebook.pk}/pages")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        result_data = resp.data.get("results", resp.data)
        result_ids = {item["id"] for item in result_data}
        self.assertIn(str(page1.pk), result_ids)
        self.assertIn(str(page2.pk), result_ids)

    def test_update_page_canvas_state(self):
        page = NotebookPage.objects.create(notebook=self.notebook, page_number=1, canvas_state={})
        resp = self.client.patch(
            f"/api/v1/notebooks/{self.notebook.pk}/pages/{page.pk}",
            {"canvas_state": {"strokes": [{"id": "s1", "points": [10, 10, 20, 20]}]}},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["canvas_state"]["strokes"][0]["id"], "s1")

    def test_delete_page(self):
        page = NotebookPage.objects.create(notebook=self.notebook, page_number=1)
        resp = self.client.delete(f"/api/v1/notebooks/{self.notebook.pk}/pages/{page.pk}")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(NotebookPage.objects.filter(pk=page.pk).exists())


class NotebookLineTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="carol@example.com", password="pass123")
        self.profile = Profile.objects.create(user=self.user, name="Carol")
        self.subject = Subject.objects.create(profile=self.profile, name="Chemistry")
        self.notebook = Notebook.objects.create(profile=self.profile, subject=self.subject, title="Chem Notes")
        self.page = NotebookPage.objects.create(notebook=self.notebook, page_number=1)
        self.client.force_authenticate(self.user)

    def test_append_strokes(self):
        resp = self.client.post(
            f"/api/v1/notebooks/{self.notebook.pk}/pages/{self.page.pk}/lines",
            [
                {"line_index": 0, "points": [10, 10, 20, 20, 30, 30], "color": "#FF0000", "width": 3.0, "tool": "pen"},
                {"line_index": 1, "points": [40, 40, 50, 50], "color": "#00FF00", "tool": "highlighter"},
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0]["color"], "#FF0000")
        self.assertEqual(resp.data[1]["tool"], "highlighter")

    def test_list_lines(self):
        NotebookLine.objects.create(page=self.page, line_index=0, points=[1, 2, 3, 4], color="#000")
        NotebookLine.objects.create(page=self.page, line_index=1, points=[5, 6, 7, 8], color="#111")

        resp = self.client.get(f"/api/v1/notebooks/{self.notebook.pk}/pages/{self.page.pk}/lines")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)


class NotebookRLSTests(TransactionTestCase):
    """Row-Level Security: users must only see their own notebooks.
    
    Using TransactionTestCase to ensure proper isolation between users.
    """
    reset_sequences = True

    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user(email="alice@example.com", password="pass123")
        self.alice_profile = Profile.objects.create(user=self.alice, name="Alice")
        self.bob = User.objects.create_user(email="bob@example.com", password="pass123")
        self.bob_profile = Profile.objects.create(user=self.bob, name="Bob")
        self.alice_subject = Subject.objects.create(profile=self.alice_profile, name="Math")
        self.bob_subject = Subject.objects.create(profile=self.bob_profile, name="Math")
        self.alice_nb = Notebook.objects.create(profile=self.alice_profile, subject=self.alice_subject, title="Alice's Notebook")
        self.bob_nb = Notebook.objects.create(profile=self.bob_profile, subject=self.bob_subject, title="Bob's Notebook")

    def test_alice_cannot_see_bob_notebook(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.get(f"/api/v1/notebooks/{self.bob_nb.pk}")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_alice_cannot_list_bob_notebooks(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.get("/api/v1/notebooks")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Alice should only see her own notebook
        result_data = resp.data.get("results", resp.data)
        result_ids = {item["id"] for item in result_data}
        self.assertIn(str(self.alice_nb.pk), result_ids)
        self.assertNotIn(str(self.bob_nb.pk), result_ids)

    def test_alice_cannot_create_page_in_bob_notebook(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            f"/api/v1/notebooks/{self.bob_nb.pk}/pages",
            {"notebook": str(self.bob_nb.pk), "page_number": 1},
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_alice_cannot_update_bob_notebook(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.patch(
            f"/api/v1/notebooks/{self.bob_nb.pk}",
            {"title": "Hacked"},
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_alice_cannot_delete_bob_notebook(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.delete(f"/api/v1/notebooks/{self.bob_nb.pk}")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)