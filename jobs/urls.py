"""Routes for the public jobs pages, the sponsor-champion console, and the
key-authenticated write API.

Neapolitan only names its URLs after `url_base`; the public list/detail routes
use different names so they cannot be confused with the console's. The console
lives at /jobs/manage/, the public pages at /jobs/ and /jobs/<pk>/, and the
write API at /jobs/api/jobs/. One-off creation from the corporate-sponsor
console lives at /corporate-sponsors/<pk>/jobs/new/ (issue #231).
"""

from django.urls import path

from .api import job_api
from .views import JobChampionView, SponsorJobCreateView, job_detail, job_list

urlpatterns = [
    path("jobs/api/jobs/", job_api, name="jobs-api-create"),
    path("jobs/api/jobs/<int:pk>/", job_api, name="jobs-api-update"),
    # Console-side one-off creation (issue #231): a corporate-sponsorship
    # manager adds a job for the sponsor whose page they are on. Declared
    # before the champion console's generated routes so it can never be
    # shadowed, though the literal `corporate-sponsors/` prefix already
    # keeps the two apart.
    path(
        "corporate-sponsors/<int:sponsor_pk>/jobs/new/",
        SponsorJobCreateView.as_view(),
        name="corporate-sponsors-job-create",
    ),
    path("jobs/", job_list, name="jobs-public-list"),
    path("jobs/<int:pk>/", job_detail, name="jobs-public-detail"),
    *JobChampionView.get_urls(),
]
