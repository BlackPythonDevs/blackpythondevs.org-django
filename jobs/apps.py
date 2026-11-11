from django.apps import AppConfig


class JobsConfig(AppConfig):
    """Corporate-sponsor job postings.

    Jobs are attached to a `corporate_sponsorships.Sponsor`. The key-
    authenticated feed API is a later part of #222.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "jobs"
    verbose_name = "Jobs"
