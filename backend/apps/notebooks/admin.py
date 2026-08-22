from django.contrib import admin

from apps.notebooks.models import Notebook, NotebookPage, NotebookLine


@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "subject", "title", "created_at", "updated_at")
    list_filter = ("subject", "created_at")
    search_fields = ("title", "description", "profile__user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("profile", "subject")


@admin.register(NotebookPage)
class NotebookPageAdmin(admin.ModelAdmin):
    list_display = ("id", "notebook", "page_number", "created_at", "updated_at")
    list_filter = ("notebook__profile",)
    search_fields = ("notebook__title",)
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("notebook",)


@admin.register(NotebookLine)
class NotebookLineAdmin(admin.ModelAdmin):
    list_display = ("id", "page", "line_index", "color", "width", "tool", "created_at")
    list_filter = ("tool", "page__notebook__profile")
    search_fields = ("page__notebook__title",)
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("page",)