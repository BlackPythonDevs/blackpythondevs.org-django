"""Grant the Discord messaging role when a member connects their account."""

import logging

from allauth.socialaccount.signals import social_account_added, social_account_updated
from django.contrib import messages
from django.dispatch import receiver

from .discord import grant_member_access, is_configured

logger = logging.getLogger(__name__)

OUTCOME_MESSAGES = {
    "added": "You've been added to the Black Python Devs Discord — welcome!",
    "role_granted": "Your Discord account now has access to post in the community server.",
}


@receiver(social_account_added)
@receiver(social_account_updated)
def handle_discord_connection(request, sociallogin, **kwargs):
    if sociallogin.account.provider != "discord":
        return

    if not is_configured():
        # No bot configured: the member still connected fine, they just follow
        # the invite link manually.
        return

    access_token = getattr(sociallogin.token, "token", None)
    if not access_token:
        logger.warning("No Discord access token for account %s", sociallogin.account.uid)
        return

    outcome = grant_member_access(sociallogin.account.uid, access_token)

    if message := OUTCOME_MESSAGES.get(outcome):
        messages.success(request, message)
    elif outcome == "failed":
        messages.warning(
            request,
            "We connected your Discord account but couldn't set up your server access. "
            "Please reach out to us and we'll sort it out.",
        )
