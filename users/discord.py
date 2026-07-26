"""Discord guild membership and role assignment.

When a member connects their Discord account we add them to the community
server and give them the role that permits messaging. This needs a bot in the
server with the *Manage Roles* permission, and the bot's role must sit above
the member role in the server's role hierarchy.

Every function here fails soft: Discord being unreachable or misconfigured must
never break the member's session.
"""

import logging

import requests
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.models import SocialApp
from django.conf import settings

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
TIMEOUT = 10


def is_configured():
    """True when guild, bot token, and role are all set."""
    return bool(
        getattr(settings, "DISCORD_GUILD_ID", "")
        and getattr(settings, "DISCORD_BOT_TOKEN", "")
        and getattr(settings, "DISCORD_MEMBER_ROLE_ID", "")
    )


def login_available(request):
    """True when a Discord OAuth app exists, so connecting an account works.

    This is separate from is_configured(): the OAuth app powers the login/
    connect flow, while the bot token and role power granting server access.
    Without an app, allauth's provider_login_url raises SocialApp.DoesNotExist.
    """
    try:
        get_adapter(request).get_app(request, "discord")
    except SocialApp.DoesNotExist:
        return False
    return True


def _headers():
    return {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def grant_member_access(discord_user_id, access_token):
    """Add the user to the guild with the member role, or grant the role if
    they're already in the server.

    Returns one of "added", "role_granted", "skipped", or "failed".
    """
    if not is_configured():
        logger.debug("Discord integration not configured; skipping role grant.")
        return "skipped"

    guild_id = settings.DISCORD_GUILD_ID
    role_id = settings.DISCORD_MEMBER_ROLE_ID

    # PUT .../members returns 201 when it adds the user and 204 when they were
    # already a member — in which case the `roles` body is ignored, so the role
    # has to be applied separately.
    try:
        response = requests.put(
            f"{DISCORD_API}/guilds/{guild_id}/members/{discord_user_id}",
            headers=_headers(),
            json={"access_token": access_token, "roles": [role_id]},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("Discord guild join failed for %s", discord_user_id)
        return "failed"

    if response.status_code == 201:
        logger.info("Added Discord user %s to guild %s with role %s", discord_user_id, guild_id, role_id)
        return "added"

    if response.status_code == 204:
        return "role_granted" if add_role(discord_user_id) else "failed"

    logger.warning(
        "Discord guild join returned %s for %s: %s",
        response.status_code,
        discord_user_id,
        response.text[:200],
    )
    return "failed"


def add_role(discord_user_id):
    """Grant the member role to someone already in the guild."""
    if not is_configured():
        return False

    try:
        response = requests.put(
            f"{DISCORD_API}/guilds/{settings.DISCORD_GUILD_ID}"
            f"/members/{discord_user_id}/roles/{settings.DISCORD_MEMBER_ROLE_ID}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("Discord role grant failed for %s", discord_user_id)
        return False

    if response.status_code == 204:
        logger.info("Granted Discord role to %s", discord_user_id)
        return True

    logger.warning(
        "Discord role grant returned %s for %s: %s",
        response.status_code,
        discord_user_id,
        response.text[:200],
    )
    return False
