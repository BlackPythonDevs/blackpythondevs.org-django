from django.apps import AppConfig


class JobsConfig(AppConfig):
    """Corporate-sponsor job postings.

    Jobs are attached to a `corporate_sponsorships.Sponsor`. This part only
    defines storage + admin; ingestion and public pages come later (#222).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "jobs"
    verbose_name = "Jobs"
