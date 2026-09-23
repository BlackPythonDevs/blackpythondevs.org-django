"""The Executorship Election page (public) and the self-service candidacy
statement form (gated to council members — see `core.models.is_council_member`).
"""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View

from core.models import is_council_member

from .forms import CandidacyForm
from .models import Candidacy, Election


def election_detail(request):
    """The election page: intro, countdown, and one card per candidate.

    Public — anyone can see who's running. `?year=` picks a past cycle;
    an absent or invalid value falls back to the most recent one, same as
    `nominations.views.NominationListView.get_term_year`.
    """
    election = None
    year = request.GET.get("year")
    if year:
        try:
            election = Election.objects.filter(year=int(year)).first()
        except ValueError:
            election = None
    if election is None:
        election = Election.objects.order_by("-year").first()

    context = {"election": election}
    if election is not None:
        context["candidacies"] = election.candidacies.select_related("user", "user__leader_profile")
        context["years"] = Election.objects.order_by("-year").values_list("year", flat=True)
        next_deadline = election.next_deadline
        if next_deadline is not None:
            context["next_deadline_label"], when = next_deadline
            context["next_deadline_iso"] = when.isoformat()
        # Drives "Write" vs "Update"/"Remove" on the CTA — only meaningful
        # for a council member, and only they could have one anyway.
        if is_council_member(request.user):
            context["user_candidacy"] = election.candidacies.filter(user=request.user).first()

    return render(request, "elections/election_detail.html", context)


class CouncilMemberRequiredMixin(UserPassesTestMixin):
    """Only sitting council members (and superusers) get in.

    Mirrors `nominations.views.LeadershipRequiredMixin`: a signed-in member
    who isn't on the council gets a 403 rather than a login redirect.
    """

    def test_func(self):
        return is_council_member(self.request.user)

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class NominatingWindowRequiredMixin(CouncilMemberRequiredMixin):
    """Only reachable while the latest election is accepting nominations.

    Shared by `CandidacyEditView` and `CandidacyRemoveView` so a statement
    can't be changed *or* withdrawn once that window has closed — what's
    shown during voting shouldn't be able to shift under it either way.
    """

    success_url = reverse_lazy("elections:detail")

    def dispatch(self, request, *args, **kwargs):
        self.election = Election.objects.order_by("-year").first()
        if self.election is None or self.election.phase != Election.NOMINATING:
            messages.error(request, "Nominations aren't open right now.")
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class CandidacyEditView(NominatingWindowRequiredMixin, View):
    """Create-or-update: a council member's statement for the latest election."""

    def get_candidacy(self):
        try:
            return Candidacy.objects.get(election=self.election, user=self.request.user)
        except Candidacy.DoesNotExist:
            return Candidacy(election=self.election, user=self.request.user)

    def get(self, request, *args, **kwargs):
        form = CandidacyForm(instance=self.get_candidacy())
        return render(request, "elections/candidacy_form.html", {"form": form, "election": self.election})

    def post(self, request, *args, **kwargs):
        form = CandidacyForm(request.POST, instance=self.get_candidacy())
        if form.is_valid():
            form.save()
            messages.success(request, "Your candidacy statement has been saved.")
            return redirect(self.success_url)
        return render(request, "elections/candidacy_form.html", {"form": form, "election": self.election})


class CandidacyRemoveView(NominatingWindowRequiredMixin, View):
    """Confirm-then-delete: a council member withdraws their own statement.

    Same shape as `communities.views.LeaveCommunityView` — a GET shows the
    confirmation, the actual delete only happens on POST.
    """

    def get_candidacy(self):
        return get_object_or_404(Candidacy, election=self.election, user=self.request.user)

    def get(self, request, *args, **kwargs):
        return render(request, "elections/candidacy_remove_confirm.html", {"candidacy": self.get_candidacy()})

    def post(self, request, *args, **kwargs):
        self.get_candidacy().delete()
        messages.success(request, "Your candidacy statement has been removed.")
        return redirect(self.success_url)
