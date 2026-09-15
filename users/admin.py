from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("email", "username", "display_name", "is_staff")
    search_fields = ("email", "username", "display_name")
    ordering = ("email",)
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "pronouns", "bio")}),
        (
            "Onboarding",
            {
                "fields": (
                    "member_type",
                    "country",
                    "region",
                    "subcommunities",
                    "communication_preferences",
                    "onboarding_completed_at",
                )
            },
        ),
    )
    readonly_fields = ("region", "onboarding_completed_at")
