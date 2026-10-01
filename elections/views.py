"""The Executorship Election page (public) and the self-service candidacy
statement form (gated to council members — see `core.models.is_council_member`).
"""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View

from core.models import is_council_member
from users.regions import continent_for_region

from .forms import BallotForm, CandidacyForm
from .models import Ballot, BallotRanking, Candidacy, Election, VoteRecord, regional_results


def group_by_continent(by_region):
    """`{region: value}` -> `[(continent, [(region, value), ...]), ...]`,
    sorted by continent then region — shared by the ballot page (grouping
    candidates) and the results page (grouping each region's tally), so a
    voter or council member sees the same continent headers in both."""
    by_continent = {}
    for region, value in by_region.items():
        by_continent.setdefault(continent_for_region(region), []).append((region, value))
    return sorted((continent, sorted(regions)) for continent, regions in by_continent.items())


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
        candidacies = election.candidacies.select_related("user", "user__leader_profile")
        context["candidacies"] = candidacies
        # Same continent -> region grouping the ballot uses.
        by_region = {}
        for candidacy in candidacies:
            by_region.setdefault(candidacy.user.region or "Unspecified region", []).append(candidacy)
        context["sections"] = group_by_continent(by_region)
        context["years"] = Election.objects.order_by("-year").values_list("year", flat=True)
        next_deadline = election.next_deadline
        if next_deadline is not None:
            context["next_deadline_label"], when = next_deadline
            context["next_deadline_iso"] = when.isoformat()
        # Drives "Write" vs "Update"/"Remove" on the CTA — only meaningful
        # for a council member, and only they could have one anyway.
        if is_council_member(request.user):
            context["user_candidacy"] = election.candidacies.filter(user=request.user).first()
            if election.phase == Election.VOTING:
                context["has_voted"] = election.has_voted(request.user)

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


class VotingWindowRequiredMixin(CouncilMemberRequiredMixin):
    """Only reachable while the latest election is in its voting window,
    and only for a council member who hasn't already cast a ballot.

    Checked against `Election.has_voted` (backed by `VoteRecord`), never
    against `Ballot` — see that model's docstring for why.
    """

    success_url = reverse_lazy("elections:detail")

    def dispatch(self, request, *args, **kwargs):
        self.election = Election.objects.order_by("-year").first()
        if self.election is None or self.election.phase != Election.VOTING:
            messages.error(request, "Voting isn't open right now.")
            return redirect(self.success_url)
        if request.user.is_authenticated and self.election.has_voted(request.user):
            messages.info(request, "You've already voted in this election.")
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class BallotCastView(VotingWindowRequiredMixin, View):
    """Cast one anonymous ballot, ranking each region's candidates for that
    region's own race — see `elections.models.regional_results`. Sections
    aren't just a display grouping here: a region's ranking only ever
    competes against candidates in that same region.
    """

    def get_candidacies(self):
        return self.election.candidacies.select_related("user", "user__leader_profile").order_by(
            "user__region", "user__display_name"
        )

    def get_sections(self, form):
        """Candidates grouped by region and then by continent — see
        `elections.views.group_by_continent`."""
        by_region = {}
        for candidacy in form.candidacies:
            region = candidacy.user.region or "Unspecified region"
            by_region.setdefault(region, []).append((candidacy, form[f"rank_{candidacy.pk}"]))
        return group_by_continent(by_region)

    def get(self, request, *args, **kwargs):
        form = BallotForm(candidacies=self.get_candidacies())
        return render(
            request,
            "elections/ballot_form.html",
            {"form": form, "election": self.election, "sections": self.get_sections(form)},
        )

    def post(self, request, *args, **kwargs):
        form = BallotForm(request.POST, candidacies=self.get_candidacies())
        if form.is_valid():
            with transaction.atomic():
                ballot = Ballot.objects.create(election=self.election)
                BallotRanking.objects.bulk_create(
                    BallotRanking(ballot=ballot, candidacy=candidacy, rank=rank) for candidacy, rank in form.rankings()
                )
                VoteRecord.objects.create(election=self.election, user=request.user)
            messages.success(request, "Your ballot has been cast anonymously. Thank you for voting.")
            return redirect(self.success_url)
        return render(
            request,
            "elections/ballot_form.html",
            {"form": form, "election": self.election, "sections": self.get_sections(form)},
        )


class ResultsView(CouncilMemberRequiredMixin, View):
    """Each region's instant-runoff winner and final vote counts —
    council-only, and only once voting has closed. Ballots stay anonymous
    throughout: this reads `Ballot`/`BallotRanking`, never `VoteRecord`.

    Shows only the deciding round, not the full round-by-round elimination
    log — the tally still runs every round internally (see
    `elections.models.tally_irv`), this just reports where it landed.
    """

    def get(self, request, *args, **kwargs):
        election = get_object_or_404(Election, year=kwargs["year"])
        if election.phase != Election.CLOSED:
            messages.error(request, "Results aren't available until voting has closed.")
            return redirect("elections:detail")
        final_rounds = {region: rounds[-1] for region, rounds in regional_results(election).items()}
        sections = group_by_continent(final_rounds)
        return render(request, "elections/results.html", {"election": election, "sections": sections})
