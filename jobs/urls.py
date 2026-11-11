"""Routes for the public jobs pages and the sponsor-champion console.

Neapolitan only names its URLs after `url_base`; the public list/detail routes
use different names so they cannot be confused with the console's. The console
lives at /jobs/manage/ and the public pages at /jobs/ and /jobs/<pk>/.
"""

from django.urls import path

from .views import JobChampionView, job_detail, job_list

urlpatterns = [
    path("jobs/", job_list, name="jobs-public-list"),
    path("jobs/<int:pk>/", job_detail, name="jobs-public-detail"),
    *JobChampionView.get_urls(),
]
