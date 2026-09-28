from django.contrib import admin

from .forms import ElectionAdminForm
from .models import Ballot, BallotRanking, Candidacy, Election, VoteRecord


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    form = ElectionAdminForm
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
        ("Nomination window", {"fields": ("nomination_opens", "nomination_closes")}),
        ("Voting window", {"fields": ("voting_opens", "voting_closes")}),
    )


@admin.register(Candidacy)
class CandidacyAdmin(admin.ModelAdmin):
    list_display = ("user", "election", "updated_at")
    list_filter = ("election",)
    search_fields = ("statement", "user__display_name", "user__email")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


class BallotRankingInline(admin.TabularInline):
    model = BallotRanking
    extra = 0
    autocomplete_fields = ("candidacy",)
    can_delete = False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Ballot)
class BallotAdmin(admin.ModelAdmin):
    """Read-only: a ballot's rankings are the tally's raw data, and nothing
    here identifies who cast it (see `elections.models.Ballot`), so there's
    nothing to edit — only to inspect for the tally."""

    list_display = ("token", "election", "submitted_at")
    list_filter = ("election",)
    readonly_fields = ("election", "token", "submitted_at")
    inlines = [BallotRankingInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(VoteRecord)
class VoteRecordAdmin(admin.ModelAdmin):
    """Who has voted, not how — see `elections.models.VoteRecord`."""

    list_display = ("user", "election", "voted_at")
    list_filter = ("election",)
    search_fields = ("user__display_name", "user__email")
    readonly_fields = ("election", "user", "voted_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
