from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.clickjacking import xframe_options_sameorigin
from neapolitan.views import CRUDView

from .forms import SponsorForm
from .models import Sponsor


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
    filterset_fields = ["status", "active"]
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
