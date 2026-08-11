"""Front-end CRUD for sponsorship requests, built on neapolitan.

This is a public-URL management surface (outside the Wagtail/Django admins) for
the Executor group. Access is gated by the same model permissions the Executor
group already holds (see migration 0003); superusers pass automatically, and
anyone else is bounced to the login screen.
"""

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from neapolitan.views import CRUDView

from .forms import PublicSponsorshipRequestForm, SponsorshipRequestForm
from .models import SponsorshipRequest


class SponsorshipRequestView(PermissionRequiredMixin, CRUDView):
    model = SponsorshipRequest
    url_base = "sponsorships"

    # Status, paid, year and region are managed elsewhere / derived, so they
    # stay off the request form (see SponsorshipRequestForm.Meta.fields).
    form_class = SponsorshipRequestForm
    fields = ["name", "url", "prospectus_url", "start_date", "country", "amount_requested", "notes"]
    filterset_fields = ["status", "country", "year"]
    paginate_by = 25

    # Requiring the full set keeps this a management console: only users who can
    # do everything (the Executor group and superusers) get in at all.
    permission_required = [
        "sponsorships.view_sponsorshiprequest",
        "sponsorships.add_sponsorshiprequest",
        "sponsorships.change_sponsorshiprequest",
        "sponsorships.delete_sponsorshiprequest",
    ]


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
    template_name = "sponsorships/request_form.html"
    success_url = reverse_lazy("sponsorship-request-done")


class SponsorshipRequestDoneView(TemplateView):
    template_name = "sponsorships/request_done.html"
