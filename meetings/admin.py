from django.contrib import admin

from .models import Meeting


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "scheduled_at", "location", "url", "updated_at")
    search_fields = ("title", "location", "notes")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "scheduled_at")}),
        ("Where", {"fields": ("location", "url")}),
        ("Minutes", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
