"""Document questions endpoint tests (B2)."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.documents.models import Document
from apps.questions.models import Question


class DocumentQuestionsEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="alice@example.com", password="pass123")
        self.profile = Profile.objects.create(user=self.user, name="Alice")
        self.subject = Subject.objects.create(profile=self.profile, name="Mathematics")
        self.client.force_authenticate(self.user)

    def test_list_document_questions(self):
        """Test GET /api/v1/documents/{id}/questions returns questions for the document."""
        # Create a document
        document = Document.objects.create(
            profile=self.profile,
            subject=self.subject,
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )

        # Create some questions for this document
        q1 = Question.objects.create(
            document=document,
            source_revision_id="12345678-1234-5678-1234-567812345678",
            source_chunk_id="87654321-4321-8765-4321-876543210987",
            difficulty=Question.Difficulty.EASY,
            prompt="What is 2+2?",
            options=["3", "4", "5", "6"],
            answer_index=1,
            content_hash="abc123",
            question_key="key1",
            generation_model="mock-gpt",
            prompt_version="question_generation:v1",
        )
        q2 = Question.objects.create(
            document=document,
            source_revision_id="12345678-1234-5678-1234-567812345678",
            source_chunk_id="11111111-1111-1111-1111-111111111111",
            difficulty=Question.Difficulty.MEDIUM,
            prompt="What is the capital of France?",
            options=["London", "Berlin", "Paris", "Madrid"],
            answer_index=2,
            content_hash="def456",
            question_key="key2",
            generation_model="mock-gpt",
            prompt_version="question_generation:v1",
        )

        # Create a question for a different document (should not appear)
        other_doc = Document.objects.create(
            profile=self.profile,
            subject=self.subject,
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )
        Question.objects.create(
            document=other_doc,
            source_revision_id="22222222-2222-2222-2222-222222222222",
            source_chunk_id="33333333-3333-3333-3333-333333333333",
            difficulty=Question.Difficulty.HARD,
            prompt="Other doc question?",
            options=["A", "B", "C", "D"],
            answer_index=0,
            content_hash="other",
            question_key="other",
            generation_model="mock-gpt",
            prompt_version="question_generation:v1",
        )

        resp = self.client.get(f"/api/v1/documents/{document.pk}/questions")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Should return paginated results
        result_data = resp.data.get("results", resp.data)
        self.assertEqual(len(result_data), 2)

        # Check the questions are correct
        question_ids = {item["id"] for item in result_data}
        self.assertIn(str(q1.pk), question_ids)
        self.assertIn(str(q2.pk), question_ids)

        # Check question structure
        q_data = result_data[0]
        self.assertIn("prompt", q_data)
        self.assertIn("options", q_data)
        self.assertIn("answer_index", q_data)
        self.assertIn("answer_text", q_data)
        self.assertIn("difficulty", q_data)

    def test_list_questions_for_nonexistent_document(self):
        """Test 404 for non-existent document."""
        import uuid
        fake_id = uuid.uuid4()
        resp = self.client.get(f"/api/v1/documents/{fake_id}/questions")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_questions_for_other_user_document(self):
        """Test 404 when trying to access another user's document."""
        other_user = User.objects.create_user(email="bob@example.com", password="pass123")
        other_profile = Profile.objects.create(user=other_user, name="Bob")
        other_doc = Document.objects.create(
            profile=other_profile,
            subject=self.subject,
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )

        resp = self.client.get(f"/api/v1/documents/{other_doc.pk}/questions")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_empty_questions_list(self):
        """Test empty list when document has no questions."""
        document = Document.objects.create(
            profile=self.profile,
            subject=self.subject,
            source=Document.Source.UPLOAD,
            source_type=Document.SourceType.IMAGE,
        )

        resp = self.client.get(f"/api/v1/documents/{document.pk}/questions")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        result_data = resp.data.get("results", resp.data)
        self.assertEqual(len(result_data), 0)