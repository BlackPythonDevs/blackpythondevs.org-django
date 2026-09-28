"""Front-end for council nominations, open to the leadership groups.

This is a members-area surface rather than an admin one: leaders sign in, see
the nominations for the current cycle, and put someone forward. Access is gated
on membership of the "Leadership Council" / "Leadership" groups, not on model
permissions — those groups deliberately carry none.

Anonymous visitors are sent to the login page; signed-in members who aren't in
leadership get a 403 rather than a login loop.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from core.models import is_leadership_or_above

from .forms import CouncilNominationForm, NominationObjectionForm
from .models import CouncilNomination, can_nominate, current_term_year


class LeadershipRequiredMixin(UserPassesTestMixin):
    """Only council members and leaders (and superusers) get in."""

    def test_func(self):
        return can_nominate(self.request.user)

    def handle_no_permission(self):
        # AccessMixin redirects to login by default, which would bounce a
        # signed-in non-leader back and forth. Raise instead once we know who
        # they are.
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class LeadershipOrExecutiveRequiredMixin(UserPassesTestMixin):
    """Council members and Executors (and superusers) get in.

    A wider tier than `LeadershipRequiredMixin`: seconding is still
    Council-only (`CouncilNomination.can_second`), but viewing a nomination,
    objecting during its window, and sending the confirmation are Council
    *and* Executor decisions.
    """

    def test_func(self):
        return is_leadership_or_above(self.request.user)

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class NominationListView(LeadershipRequiredMixin, ListView):
    """Every nomination in one cycle, newest first."""

    model = CouncilNomination
    template_name = "nominations/nomination_list.html"
    context_object_name = "nominations"
    paginate_by = 25

    def get_term_year(self):
        """The cycle being viewed — `?year=` overrides, otherwise this year."""
        try:
            return int(self.request.GET["year"])
        except (KeyError, ValueError):
            return current_term_year()

    def get_queryset(self):
        return (
            CouncilNomination.objects.filter(term_year=self.get_term_year())
            .select_related("nominator", "nominee_user")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["term_year"] = self.get_term_year()
        context["years"] = (
            CouncilNomination.objects.order_by("-term_year").values_list("term_year", flat=True).distinct()
        )
        return context


class NominateView(LeadershipRequiredMixin, CreateView):
    """The nomination form itself."""

    model = CouncilNomination
    form_class = CouncilNominationForm
    template_name = "nominations/nomination_form.html"
    success_url = reverse_lazy("nominations:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["nominator"] = self.request.user
        kwargs["term_year"] = current_term_year()
        return kwargs

    def form_valid(self, form):
        form.instance.nominator = self.request.user
        form.instance.term_year = current_term_year()
        response = super().form_valid(form)
        messages.success(self.request, f"Nomination submitted for {self.object.nominee_name}.")
        return response


class NominationDetailView(LeadershipOrExecutiveRequiredMixin, DetailView):
    model = CouncilNomination
    template_name = "nominations/nomination_detail.html"

    def get_queryset(self):
        return CouncilNomination.objects.select_related("nominator", "nominee_user", "seconded_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # These all take an argument, so templates can't call them directly.
        context["can_edit"] = self.object.editable_by(self.request.user)
        context["can_second"] = self.object.can_second(self.request.user)
        context["can_object"] = self.object.can_object(self.request.user)
        context["objections"] = self.object.objections.select_related("submitted_by")
        return context


class NominationUpdateView(LeadershipRequiredMixin, UpdateView):
    """Nominators tidy up their own wording while the nomination is open."""

    model = CouncilNomination
    form_class = CouncilNominationForm
    template_name = "nominations/nomination_form.html"

    def get_object(self, queryset=None):
        nomination = super().get_object(queryset)
        if not nomination.editable_by(self.request.user):
            raise PermissionDenied("You can only edit your own open nominations.")
        return nomination

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["nominator"] = self.object.nominator
        kwargs["term_year"] = self.object.term_year
        return kwargs

    def get_success_url(self):
        return reverse("nominations:detail", args=[self.object.pk])


class NominationWithdrawView(LeadershipRequiredMixin, View):
    """POST-only: the nominator withdraws their own open nomination.

    Withdrawing keeps the record — the council's history of who was put forward
    shouldn't disappear — it just moves the status.
    """

    def post(self, request, pk):
        nomination = get_object_or_404(CouncilNomination, pk=pk)
        if not nomination.editable_by(request.user):
            raise PermissionDenied("You can only withdraw your own open nominations.")
        nomination.status = CouncilNomination.WITHDRAWN
        nomination.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Withdrew the nomination for {nomination.nominee_name}.")
        return redirect("nominations:detail", pk=nomination.pk)


class NominationSecondView(LeadershipRequiredMixin, View):
    """POST-only: another Council-tier leader seconds an open nomination,
    which opens the 24-hour objection window."""

    def post(self, request, pk):
        nomination = get_object_or_404(CouncilNomination, pk=pk)
        if not nomination.can_second(request.user):
            raise PermissionDenied("You can't second this nomination.")
        nomination.second(request.user)
        messages.success(
            request,
            f"Seconded the nomination for {nomination.nominee_name}. "
            f"Objections can be raised until {nomination.objection_window_closes_at:%d %b %Y, %H:%M} UTC.",
        )
        return redirect("nominations:detail", pk=nomination.pk)


class NominationObjectView(LeadershipOrExecutiveRequiredMixin, CreateView):
    """Council/Executor members raise an objection while the window is open.

    Objections are never shown to the nominee or the public — see
    `NominationObjection`'s docstring.
    """

    form_class = NominationObjectionForm
    template_name = "nominations/nomination_objection_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.nomination = get_object_or_404(CouncilNomination, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if not self.nomination.can_object(request.user):
            raise PermissionDenied("The objection window isn't open.")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not self.nomination.can_object(request.user):
            raise PermissionDenied("The objection window isn't open.")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["nomination"] = self.nomination
        return context

    def form_valid(self, form):
        form.instance.nomination = self.nomination
        form.instance.submitted_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Objection recorded.")
        return response

    def get_success_url(self):
        return reverse("nominations:detail", args=[self.nomination.pk])


class NominationSendConfirmationView(LeadershipOrExecutiveRequiredMixin, View):
    """POST-only: send the nominee their acceptance link, once the objection
    window has actually closed. The button that posts here may be visible
    slightly before that (a client clock can lag), so this re-checks
    server-side rather than trusting the click.
    """

    def post(self, request, pk):
        nomination = get_object_or_404(CouncilNomination, pk=pk)
        if not nomination.ready_to_confirm:
            messages.error(request, "The 24-hour objection window hasn't closed yet.")
            return redirect("nominations:detail", pk=nomination.pk)

        invite = nomination.create_confirmation_invite(request.user)
        accept_url = request.build_absolute_uri(invite.get_absolute_url())
        message = EmailMultiAlternatives(
            subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}You've been confirmed for the Leadership Council",
            body=(
                f"Hi {nomination.nominee_name},\n\n"
                "The Black Python Devs Leadership Council would like you to join as a council member.\n\n"
                f"Accept here: {accept_url}\n\n"
                "Accepting will create your account if you don't already have one, and add you to the council."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[nomination.nominee_email],
        )
        message.send()
        nomination.mark_confirmation_sent(invite)

        messages.success(request, f"Confirmation email sent to {nomination.nominee_email}.")
        return redirect("nominations:detail", pk=nomination.pk)
