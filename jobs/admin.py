"""Staff-gated Django admin for Job records.

The neapolitan/web consoles later (#222) are separate; this is the plain
admin an administrator uses to seed jobs by hand.
"""

from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "sponsor",
        "location",
        "remote",
        "employment_type",
        "status",
        "is_published",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_published", "status", "remote", "employment_type", "source")
    search_fields = ("title", "location", "sponsor__name")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
