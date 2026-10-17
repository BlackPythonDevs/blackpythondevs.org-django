"""Shared email helpers (see issue #132).

Notification-style emails (notifications.Notification and
community_messages.CommunityMessage) go out from one unmanaged mailbox that
discards replies. Every such email therefore carries a short preamble — what
the message is, who sent it, and a link to read it on the site — and a footer
warning that replies are thrown away.
"""

from django.conf import settings


# WAGTAILADMIN_BASE_URL is the canonical scheme+host for links the server
# generates outside a request (Wagtail's own password-reset emails use it for
# the same reason): send() runs in a view, but models shouldn't reach for the
# request stack to build a URL.
def absolute_url(path: str) -> str:
    """An absolute URL for `path` (a root-relative path like `/foo/`)."""
    return f"{settings.WAGTAILADMIN_BASE_URL.rstrip('/')}{path}"


UNMANAGED_MAILBOX_FOOTER = (
    "These messages are sent from an unmanaged account and replies to these messages are automatically deleted."
)
