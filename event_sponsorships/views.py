"""Front-end CRUD for sponsorship requests, built on neapolitan.

This is a public-URL management surface (outside the Wagtail/Django admins) for
the Executor group. Access is gated by the same model permissions the Executor
group already holds (see migration 0003); superusers pass automatically, and
anyone else is bounced to the login screen.
"""

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, TemplateView
from neapolitan.views import CRUDView

from .forms import PublicSponsorshipRequestForm, SponsorshipRequestForm, SponsorshipStatusForm
from .models import SponsorshipRequest


class SponsorshipRequestView(PermissionRequiredMixin, CRUDView):
    model = SponsorshipRequest
    url_base = "event-sponsorships"

    # Status, paid, year and region are managed elsewhere / derived, so they
    # stay off the request form (see SponsorshipRequestForm.Meta.fields).
    form_class = SponsorshipRequestForm
    fields = ["name", "url", "prospectus_url", "start_date", "country", "amount_requested", "notes"]
    filterset_fields = ["status", "country", "year"]
    paginate_by = 25

    # Requiring the full set keeps this a management console: only users who can
    # do everything (the Executor group and superusers) get in at all.
    permission_required = [
        "event_sponsorships.view_sponsorshiprequest",
        "event_sponsorships.add_sponsorshiprequest",
        "event_sponsorships.change_sponsorshiprequest",
        "event_sponsorships.delete_sponsorshiprequest",
    ]

    def get_context_data(self, **kwargs):
        """Add the status control to the detail page only.

        The form is unbound: the write itself is a POST to a dedicated route
        (see SponsorshipRequestStatusView), so a GET of the detail page can
        never change state. `can_change` hides the control from anyone who
        couldn't submit it anyway.
        """
        context = super().get_context_data(**kwargs)
        if self.role.url_name_component == "detail":
            context["status_form"] = SponsorshipStatusForm(instance=self.object)
            context["can_change"] = self.request.user.has_perm("event_sponsorships.change_sponsorshiprequest")
        return context


class SponsorshipRequestStatusView(PermissionRequiredMixin, View):
    """Move a sponsorship request through its lifecycle, from the console.

    POST-only (a GET is a 405) and gated on the same Executor permission the
    rest of the console uses. The submitted value is validated against
    STATUS_CHOICES by `SponsorshipStatusForm`, then written through
    `instance.save()` so django-auditlog records the actor and the field diff
    — and so the derived fields stay in step.
    """

    permission_required = "event_sponsorships.change_sponsorshiprequest"

    def post(self, request, *args, **kwargs):
        sponsorship = get_object_or_404(SponsorshipRequest, pk=kwargs["pk"])
        form = SponsorshipStatusForm(request.POST, instance=sponsorship)
        if form.is_valid():
            form.save()
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
        return redirect("event-sponsorships-detail", pk=sponsorship.pk)


class PublicSponsorshipRequestView(CreateView):
    """The public "ask us to sponsor your event" form.

    Deliberately open to anonymous visitors: the organisers who need this are
    event runners from outside the community, and the model has no user FK to
    tie a submission to an account anyway. Submissions land as `requested` and
    stay invisible until an Executor marks them completed.

    `template_name` is set explicitly — CreateView's default would resolve to
    sponsorshiprequest_form.html, which is the staff console's edit form.
    """

    model = SponsorshipRequest
    form_class = PublicSponsorshipRequestForm
    template_name = "event_sponsorships/request_form.html"
    success_url = reverse_lazy("event-sponsorship-request-done")


class SponsorshipRequestDoneView(TemplateView):
    template_name = "event_sponsorships/request_done.html"
