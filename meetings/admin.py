from django.contrib import admin

from .models import CalendarFeed, Meeting


@admin.register(CalendarFeed)
class CalendarFeedAdmin(admin.ModelAdmin):
    """The feed token itself isn't editable: rotate by deleting and letting
    a fresh one generate on next use (see CalendarFeed.current_token)."""

    list_display = ("__str__", "token")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
