"""Questions API (architecture §60).

GET /api/v1/documents/{id}/questions  — list questions for a document
"""
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.documents.models import Document
from apps.questions.models import Question
from apps.questions.serializers import QuestionSerializer
from shared.exceptions import ResourceNotFound


class DocumentQuestionsViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/v1/documents/{document_id}/questions"""

    serializer_class = QuestionSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        document_id = self.kwargs.get("document_id")
        return Question.objects.filter(
            document_id=document_id,
            document__profile__user=self.request.user,
        ).select_related("document")

    def list(self, request, *args, **kwargs):
        document_id = self.kwargs.get("document_id")
        try:
            Document.objects.get(pk=document_id, profile__user=request.user)
        except (Document.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Document not found.")

        return super().list(request, *args, **kwargs)