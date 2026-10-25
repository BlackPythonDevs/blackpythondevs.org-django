from datetime import timedelta

import django_filters
from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.clickjacking import xframe_options_sameorigin
from neapolitan.views import CRUDView

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


@cache_control(max_age=60 * 60 * 24)
@xframe_options_sameorigin
def community_map(request):
    return render(request, "core/map.html", {"carto_api_key": settings.CARTO_API_KEY})


class SponsorView(PermissionRequiredMixin, CRUDView):
    """Front-end console for corporate sponsors.

    Replaces the Wagtail snippet admin as the place to manage Sponsor
    records (see the docstring on Sponsor itself) — full CRUD, same shape as
    sponsorships.views.SponsorshipRequestView. The detail page embeds the
    corporate-sponsorship checklist via {% checklist_widget %}.
    """

    model = Sponsor
    url_base = "sponsors"
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
        "core.view_sponsor",
        "core.add_sponsor",
        "core.change_sponsor",
        "core.delete_sponsor",
    ]


@cache_control(max_age=60 * 60 * 24)
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /cms/",
        "Disallow: /django-admin/",
        "Disallow: /accounts/",
        "",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
