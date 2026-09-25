"""Front-end for Community Service Award nominations, open to leadership.

This is a members-area surface rather than an admin one: leaders sign in,
see the nominations for the current cycle, and put someone forward. Access
is gated on the Leadership Council / Executor groups (see
`core.models.is_leadership_or_above`), not on model permissions — those
groups deliberately carry none.

Anonymous visitors are sent to the login page; signed-in members who aren't
in leadership get a 403 rather than a login loop.
"""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from .forms import ServiceAwardNominationForm
from .models import ServiceAwardNomination, can_nominate, current_award_year, group_by_nominee


class LeadershipRequiredMixin(UserPassesTestMixin):
    """Only leadership (and superusers) get in."""

    def test_func(self):
        return can_nominate(self.request.user)

    def handle_no_permission(self):
        # AccessMixin redirects to login by default, which would bounce a
        # signed-in non-leader back and forth. Raise instead once we know who
        # they are.
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class NominationListView(LeadershipRequiredMixin, ListView):
    """One row per nominee in one cycle, most-supported first.

    Two leaders nominating the same person are two rows of support for one
    nominee, not two unrelated nominations, so the list groups them by email
    (see `group_by_nominee`) rather than listing every nomination record.
    """

    template_name = "service_award/nomination_list.html"
    context_object_name = "nominee_groups"
    paginate_by = 25

    def get_award_year(self):
        """The cycle being viewed — `?year=` overrides, otherwise this year."""
        try:
            return int(self.request.GET["year"])
        except (KeyError, ValueError):
            return current_award_year()

    def get_queryset(self):
        # Withdrawn nominations keep their record (see NominationWithdrawView)
        # but shouldn't clutter the list leadership works from day to day.
        nominations = (
            ServiceAwardNomination.objects.filter(award_year=self.get_award_year())
            .exclude(status=ServiceAwardNomination.WITHDRAWN)
            .select_related("nominator", "nominee_user")
            .order_by("-created_at")
        )
        return group_by_nominee(nominations)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        award_year = self.get_award_year()
        context["award_year"] = award_year
        context["years"] = (
            ServiceAwardNomination.objects.order_by("-award_year").values_list("award_year", flat=True).distinct()
        )
        # Reinstating a withdrawn nomination without resubmitting the form
        # only makes sense for the current cycle (see `reinstatable_by`), so
        # this section only shows up when that's the cycle being viewed.
        if award_year == current_award_year():
            withdrawn = ServiceAwardNomination.objects.filter(
                award_year=award_year,
                status=ServiceAwardNomination.WITHDRAWN,
            ).select_related("nominator")
            if not self.request.user.is_superuser:
                # A leader sees a withdrawn nomination here if they withdrew
                # it themselves, or if they're currently backing that same
                # nominee (see `group_by_nominee` — nominating alongside
                # someone collates into one nominee, not separate entries),
                # so they can see the full picture of support for someone
                # they're also nominating. Not everyone else's withdrawals.
                my_nominee_emails = {
                    email.strip().lower()
                    for email in ServiceAwardNomination.objects.filter(
                        nominator=self.request.user,
                        award_year=award_year,
                    )
                    .exclude(status=ServiceAwardNomination.WITHDRAWN)
                    .values_list("nominee_email", flat=True)
                }
                withdrawn = [
                    nomination
                    for nomination in withdrawn
                    if nomination.nominator_id == self.request.user.pk
                    or nomination.nominee_email.strip().lower() in my_nominee_emails
                ]
            withdrawn = sorted(withdrawn, key=lambda nomination: nomination.updated_at, reverse=True)
            context["withdrawn_nominations"] = withdrawn
            # `reinstatable_by` takes an argument, so the template can't call
            # it directly — someone else's withdrawn nomination for a
            # nominee you're also backing shows up here for visibility, but
            # you still can't be the one to bring it back.
            context["reinstatable_ids"] = {
                nomination.pk for nomination in withdrawn if nomination.reinstatable_by(self.request.user)
            }
        return context


class NominateView(LeadershipRequiredMixin, CreateView):
    """The nomination form itself."""

    model = ServiceAwardNomination
    form_class = ServiceAwardNominationForm
    template_name = "service_award/nomination_form.html"
    success_url = reverse_lazy("service_award:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["nominator"] = self.request.user
        kwargs["award_year"] = current_award_year()
        return kwargs

    def form_valid(self, form):
        form.instance.nominator = self.request.user
        form.instance.award_year = current_award_year()
        was_reinstated = form.reinstate_target is not None
        response = super().form_valid(form)
        if was_reinstated:
            messages.success(self.request, f"Reinstated the nomination for {self.object.nominee_name}.")
        else:
            messages.success(self.request, f"Nomination submitted for {self.object.nominee_name}.")
        return response


class NominationDetailView(LeadershipRequiredMixin, DetailView):
    model = ServiceAwardNomination
    template_name = "service_award/nomination_detail.html"

    def get_queryset(self):
        return ServiceAwardNomination.objects.select_related("nominator", "nominee_user")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # `editable_by` takes an argument, so templates can't call it directly.
        context["can_edit"] = self.object.editable_by(self.request.user)
        # `reinstatable_by` takes an argument too, same reasoning as `can_edit`.
        context["can_reinstate"] = self.object.reinstatable_by(self.request.user)
        # Other leaders' support for the same nominee this cycle (see
        # `group_by_nominee`) — this record's own nomination isn't repeated.
        context["supporting_nominations"] = (
            ServiceAwardNomination.objects.filter(
                nominee_email__iexact=self.object.nominee_email,
                award_year=self.object.award_year,
            )
            .exclude(pk=self.object.pk)
            .exclude(status=ServiceAwardNomination.WITHDRAWN)
            .select_related("nominator")
        )
        return context


class NominationUpdateView(LeadershipRequiredMixin, UpdateView):
    """Nominators tidy up their own wording while the nomination is open."""

    model = ServiceAwardNomination
    form_class = ServiceAwardNominationForm
    template_name = "service_award/nomination_form.html"

    def get_object(self, queryset=None):
        nomination = super().get_object(queryset)
        if not nomination.editable_by(self.request.user):
            raise PermissionDenied("You can only edit your own open nominations.")
        return nomination

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["nominator"] = self.object.nominator
        kwargs["award_year"] = self.object.award_year
        return kwargs

    def get_success_url(self):
        return reverse("service_award:detail", args=[self.object.pk])


class NominationWithdrawView(LeadershipRequiredMixin, View):
    """POST-only: the nominator withdraws their own open nomination.

    Withdrawing keeps the record — leadership's history of who was put
    forward shouldn't disappear — it just moves the status.
    """

    def post(self, request, pk):
        nomination = get_object_or_404(ServiceAwardNomination, pk=pk)
        if not nomination.editable_by(request.user):
            raise PermissionDenied("You can only withdraw your own open nominations.")
        nomination.status = ServiceAwardNomination.WITHDRAWN
        nomination.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Withdrew the nomination for {nomination.nominee_name}.")
        return redirect("service_award:detail", pk=nomination.pk)


class NominationReinstateView(LeadershipRequiredMixin, View):
    """POST-only: bring a withdrawn nomination straight back for the current
    cycle, exactly as it was, without going through the nomination form.

    This is the direct counterpart to withdrawing — the form's own
    resubmit-and-reinstate path (see `ServiceAwardNominationForm.clean`)
    still exists for when someone starts a fresh nomination for the same
    person and happens to hit an old withdrawn one; this is for going
    straight to a withdrawn nomination and bringing it back as-is.
    """

    def post(self, request, pk):
        nomination = get_object_or_404(ServiceAwardNomination, pk=pk)
        if not nomination.reinstatable_by(request.user):
            raise PermissionDenied("You can only reinstate your own withdrawn nominations from this cycle.")
        nomination.status = ServiceAwardNomination.SUBMITTED
        nomination.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Reinstated the nomination for {nomination.nominee_name}.")
        return redirect("service_award:detail", pk=nomination.pk)
