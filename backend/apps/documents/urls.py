from django.urls import include, path
from rest_framework.routers import DefaultRouter


from apps.chat.views import ChatSessionViewSet
from apps.documents.views import (
    CancelJobView,
    DigitizedDocumentViewSet,
    DigitizedDownloadView,
    DocumentViewSet,
    FinalizeUploadView,
    JobViewSet,
)
from apps.questions.views import DocumentQuestionsViewSet
from apps.retrieval.views import SearchView
from apps.revision.views import RevisionGoalsView, RevisionOverviewView, RevisionPlansView
from apps.tests.views import TestViewSet

router = DefaultRouter(trailing_slash=False)
router.register("documents", DocumentViewSet, basename="documents")
router.register("jobs", JobViewSet, basename="jobs")
router.register("digitized-documents", DigitizedDocumentViewSet, basename="digitized-documents")
router.register("tests", TestViewSet, basename="tests")
router.register("chat/sessions", ChatSessionViewSet, basename="chat-sessions")

document_questions = DocumentQuestionsViewSet.as_view({"get": "list"})

urlpatterns = [
    path("", include(router.urls)),
    path("documents/pages/<uuid:page_id>/finalize-upload", FinalizeUploadView.as_view(), name="finalize-upload"),
    path("digitized-documents/<uuid:pk>/download", DigitizedDownloadView.as_view(), name="digitized-download"),
    path("jobs/<uuid:pk>/cancel", CancelJobView.as_view(), name="job-cancel"),
    path("search", SearchView.as_view(), name="search"),
    path("documents/<uuid:document_id>/questions", document_questions, name="document-questions"),
    path("", include("apps.audit.urls")),
    path("revision/overview", RevisionOverviewView.as_view(), name="revision-overview"),
    path("revision/goals", RevisionGoalsView.as_view(), name="revision-goals"),
    path("revision/plans", RevisionPlansView.as_view(), name="revision-plans"),
]
