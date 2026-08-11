from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ambassadors.models import StudentAmbassador
from nominations.models import can_nominate

from .discord import is_configured, login_available


@login_required
def members(request):
    """The member area: profile summary and Discord connection status."""
    return render(
        request,
        "users/members.html",
        {
            "discord_account": SocialAccount.objects.filter(user=request.user, provider="discord").first(),
            "discord_invite_url": settings.DISCORD_INVITE_URL,
            # Whether connecting actually grants the messaging role, or just links.
            "discord_role_enabled": is_configured(),
            # Whether a Discord OAuth app exists, so the connect flow can run.
            "discord_login_available": login_available(request),
            # Their ambassador application, if they've started one.
            "ambassador_application": StudentAmbassador.objects.filter(user=request.user).first(),
            # Council/Leadership members get the nominations panel.
            "can_nominate": can_nominate(request.user),
        },
    )
