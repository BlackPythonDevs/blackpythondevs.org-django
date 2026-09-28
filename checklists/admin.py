"""Superuser-only oversight of raw Task/Note rows.

Day-to-day use is the front-end portal (views.py); this is just for
debugging — finding an orphaned row, checking what a bulk edit actually
wrote, etc.
"""

from django.contrib import admin

from .models import Note, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "linked_object", "is_default", "is_done", "done_by", "done_at", "due_date", "assigned_to")
    list_filter = ("is_default", "is_done", "content_type")
    search_fields = ("title",)
    autocomplete_fields = ("done_by", "assigned_to")

    @admin.display(description="On")
    def linked_object(self, obj):
        return obj.content_object


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("linked_object", "created_by", "created_at")
    list_filter = ("content_type",)
    search_fields = ("body",)
    autocomplete_fields = ("created_by",)

    @admin.display(description="On")
    def linked_object(self, obj):
        return obj.content_object
