"""Front-end CRUD for sponsorship requests, built on neapolitan.

This is a public-URL management surface (outside the Wagtail/Django admins) for
the Executor group. Access is gated by the same model permissions the Executor
group already holds (see migration 0003); superusers pass automatically, and
anyone else is bounced to the login screen.
"""

from django.contrib.auth.mixins import PermissionRequiredMixin
from neapolitan.views import CRUDView

from .forms import SponsorshipRequestForm
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
