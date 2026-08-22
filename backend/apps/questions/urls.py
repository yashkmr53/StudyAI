from django.urls import path

from apps.questions.views import DocumentQuestionsViewSet

document_questions = DocumentQuestionsViewSet.as_view({"get": "list"})

urlpatterns = [
    path("documents/<uuid:document_id>/questions", document_questions, name="document-questions"),
]