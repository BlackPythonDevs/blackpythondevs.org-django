from datetime import timedelta

import django_filters
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from neapolitan.views import CRUDView

from core.models import is_corporate_sponsor

from .forms import SponsorForm
from .models import Sponsor

# Fixed choices for the expiry-window filter: a sponsor whose contract ends
# within this many days needs chasing for a renewal. Deliberately a small,
# fixed set so the querystring value is validated before it ever reaches the
# ORM (issue #85).
EXPIRY_WINDOW_CHOICES = [
    ("30", "Expiring in the next 30 days"),
    ("60", "Expiring in the next 60 days"),
]


class SponsorFilterSet(django_filters.FilterSet):
    """Filters for the sponsor console's list view ("health at a glance").

    In addition to the status/active filters neapolitan derives from
    `filterset_fields`, lets Executors pull up every sponsor expiring within
    the next 30 or 60 days without opening each record.
    """

    expires_within = django_filters.ChoiceFilter(
        label="Expiry window",
        choices=EXPIRY_WINDOW_CHOICES,
        method="filter_expires_within",
        empty_label="Any expiry",
    )

    class Meta:
        model = Sponsor
        fields = ["status", "active"]

    def filter_expires_within(self, queryset, name, value):
        window_end = timezone.localdate() + timedelta(days=int(value))
        return queryset.filter(
            expires_at__gte=timezone.localdate(),
            expires_at__lte=window_end,
        )


class SponsorView(PermissionRequiredMixin, CRUDView):
    """Front-end console for corporate sponsors, at /corporate-sponsors/.

    Replaces the Wagtail snippet admin as the place to manage Sponsor
    records (see the docstring on Sponsor itself) — full CRUD, same shape as
    sponsorships.views.SponsorshipRequestView. The detail page embeds the
    corporate-sponsorship checklist via {% checklist_widget %}.
    """

    model = Sponsor
    url_base = "corporate-sponsors"
    form_class = SponsorForm
    fields = [
        "name",
        "url",
        "logo",
        "logo_static_path",
        "sort_order",
        "active",
        "status",
        "invoice_paid_date",
        "contract_amount",
        "primary_contact_name",
        "primary_contact_email",
    ]
    filterset_class = SponsorFilterSet
    paginate_by = 25

    # Requiring the full set keeps this a management console: only users who
    # can do everything (the Executor group and superusers) get in at all —
    # see sponsorships.views.SponsorshipRequestView for the same reasoning.
    permission_required = [
        "corporate_sponsorships.view_sponsor",
        "corporate_sponsorships.add_sponsor",
        "corporate_sponsorships.change_sponsor",
        "corporate_sponsorships.delete_sponsor",
    ]


@require_GET
@login_required
def my_sponsorship(request):
    """Read-only page for a member who represents a corporate sponsor (issue #203).

    Takes no identifier from the request: the Sponsor comes only from
    request.user.corporation_affiliate, so there is nothing to tamper with to
    reach another company's record. Anyone who isn't in the "Corporate
    Sponsor" group with an affiliation set gets a 404.

    The template shows an explicit allowlist of fields and never the
    internal ones (contract amount, invoice date, contacts, checklist).
    """
    if not is_corporate_sponsor(request.user):
        raise Http404
    sponsor = request.user.corporation_affiliate
    return render(request, "corporate_sponsorships/my_sponsorship.html", {"sponsor": sponsor})
