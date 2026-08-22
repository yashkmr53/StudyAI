from django.urls import path

from apps.notebooks.views import NotebookPageViewSet, NotebookViewSet

notebook_list = NotebookViewSet.as_view({"get": "list", "post": "create"})
notebook_detail = NotebookViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
notebook_pages = NotebookPageViewSet.as_view({"get": "list", "post": "create"})
notebook_page_detail = NotebookPageViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
notebook_page_lines = NotebookPageViewSet.as_view({"get": "lines", "post": "lines"})

urlpatterns = [
    path("notebooks", notebook_list, name="notebook-list"),
    path("notebooks/<uuid:pk>", notebook_detail, name="notebook-detail"),
    path("notebooks/<uuid:notebook_pk>/pages", notebook_pages, name="notebook-pages"),
    path("notebooks/<uuid:notebook_pk>/pages/<uuid:pk>", notebook_page_detail, name="notebook-page-detail"),
    path("notebooks/<uuid:notebook_pk>/pages/<uuid:pk>/lines", notebook_page_lines, name="notebook-page-lines"),
]