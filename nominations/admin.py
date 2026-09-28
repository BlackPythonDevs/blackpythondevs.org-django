from django.contrib import admin

from .models import CouncilNomination, NominationObjection


class NominationObjectionInline(admin.TabularInline):
    model = NominationObjection
    extra = 0
    readonly_fields = ("submitted_by", "reason", "created_at")
    can_delete = False


@admin.register(CouncilNomination)
class CouncilNominationAdmin(admin.ModelAdmin):
    list_display = ("nominee_name", "term_year", "nominator", "nominee_consulted", "status", "created_at")
    list_filter = ("status", "term_year", "nominee_consulted")
    search_fields = ("nominee_name", "nominee_email", "statement", "notes")
    list_editable = ("status",)
    ordering = ("-term_year", "-created_at")
    autocomplete_fields = ("nominator", "nominee_user", "seconded_by")
    readonly_fields = (
        "created_at",
        "updated_at",
        "seconded_at",
        "objection_window_closes_at",
        "confirmation_sent_at",
        "accepted_at",
        "onboarding_notified_at",
    )
    inlines = [NominationObjectionInline]
    fieldsets = (
        (None, {"fields": ("nominator", "term_year", "status")}),
        ("Nominee", {"fields": ("nominee_name", "nominee_email", "nominee_user", "nominee_url")}),
        ("The case", {"fields": ("statement", "contributions", "nominee_consulted")}),
        (
            "Seconding and confirmation",
            {
                "fields": (
                    "seconded_by",
                    "seconded_at",
                    "objection_window_closes_at",
                    "invite_link",
                    "confirmation_sent_at",
                    "accepted_at",
                    "announcement_page",
                    "onboarding_notified_at",
                )
            },
        ),
        ("Internal", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
