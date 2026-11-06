"""Routes for event sponsorships, mounted at the site root.

The console and the public intake form used to live under /sponsorships/
(issue #202 moved them to /event-sponsorships/), so the old paths still
answer with a permanent redirect to the same place under the new prefix.
"""

from urllib.parse import quote

from django.http import HttpResponsePermanentRedirect
from django.urls import path

from .views import PublicSponsorshipRequestView, SponsorshipRequestDoneView, SponsorshipRequestView

PREFIX = "/event-sponsorships/"


def legacy_sponsorships_redirect(request, rest=""):
    """301 /sponsorships/<rest> to /event-sponsorships/<rest>.

    The target is always the fixed internal prefix plus the captured suffix.
    Leading slashes and backslashes are stripped from the suffix and the rest
    is percent-encoded, so a path like /sponsorships//evil.example/ can never
    become a protocol-relative URL that leaves the site. The query string is
    carried over only as a query string; it never decides the destination.
    """
    target = PREFIX + quote(rest.lstrip("/\\"))
    query = request.META.get("QUERY_STRING", "")
    if query:
        target += "?" + quote(query, safe="=&+%;,/:@")
    return HttpResponsePermanentRedirect(target)


urlpatterns = [
    path("sponsorships/", legacy_sponsorships_redirect, name="legacy-sponsorships-redirect"),
    path("sponsorships/<path:rest>", legacy_sponsorships_redirect),
    # Public intake. Listed before the CRUD routes so these fixed paths are
    # matched before neapolitan's generated ones.
    path("event-sponsorships/request/", PublicSponsorshipRequestView.as_view(), name="event-sponsorship-request"),
    path(
        "event-sponsorships/request/thanks/",
        SponsorshipRequestDoneView.as_view(),
        name="event-sponsorship-request-done",
    ),
    # Front-end CRUD for the Executor group (neapolitan).
    *SponsorshipRequestView.get_urls(),
]
