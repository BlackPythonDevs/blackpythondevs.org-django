"""Routes for the corporate-sponsor console, mounted at the site root.

The console used to live at /sponsors/ (issue #201 moved it), so the old
paths still answer with a permanent redirect to the same place under the new
prefix.
"""

from django.http import HttpResponsePermanentRedirect
from django.urls import path

from .views import SponsorView

CONSOLE_PREFIX = "/corporate-sponsors/"


def legacy_sponsors_redirect(request, rest=""):
    """301 /sponsors/<rest> to /corporate-sponsors/<rest>.

    The target is always the fixed internal prefix plus the captured suffix.
    Leading slashes and backslashes are stripped from the suffix, so a path
    like /sponsors//evil.example/ can never turn into a protocol-relative
    URL that leaves the site. The query string is deliberately dropped.
    """
    return HttpResponsePermanentRedirect(CONSOLE_PREFIX + rest.lstrip("/\\"))


urlpatterns = [
    path("sponsors/", legacy_sponsors_redirect, name="legacy-sponsors-redirect"),
    path("sponsors/<path:rest>", legacy_sponsors_redirect),
    *SponsorView.get_urls(),
]
