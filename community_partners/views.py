from django.shortcuts import render
from django.views.decorators.http import require_safe

from .models import CommunityPartner


def _public_partner(partner):
    """Reduce a CommunityPartner to its allowlisted public values."""
    return partner.get_public_data()


@require_safe
def community_partners(request):
    """Public list of active community partners.

    Read-only and takes no identifier from the request, so there is nothing
    to tamper with. Each row is projected through the model's allowlist so
    internal fields (`notes`, timestamps) can never reach the template.
    """
    partners = [_public_partner(partner) for partner in CommunityPartner.objects.filter(is_active=True)]
    return render(request, "community_partners/community_partners.html", {"partners": partners})
