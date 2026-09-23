from django.contrib import admin

from .models import Candidacy, Election


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = (
        "year",
        "phase",
        "nomination_opens_at",
        "nomination_closes_at",
        "voting_opens_at",
        "voting_closes_at",
    )
    ordering = ("-year",)
    fieldsets = (
        (None, {"fields": ("year", "intro")}),
        ("Nomination window", {"fields": ("nomination_opens_at", "nomination_closes_at")}),
        ("Voting window", {"fields": ("voting_opens_at", "voting_closes_at")}),
    )


@admin.register(Candidacy)
class CandidacyAdmin(admin.ModelAdmin):
    list_display = ("user", "election", "updated_at")
    list_filter = ("election",)
    search_fields = ("statement", "user__display_name", "user__email")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
