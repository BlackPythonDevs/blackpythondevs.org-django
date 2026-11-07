from django.apps import AppConfig


class SponsorshipsConfig(AppConfig):
    """Migrations-only stub for the old `sponsorships` app (issue #202).

    The code moved to `event_sponsorships`. This app stays installed only so
    its historical migrations (which other apps depend on) keep resolving and
    its final migration can drop SponsorshipRequest from the old state. It
    can be removed in a later release once every database has applied it.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "sponsorships"
    verbose_name = "Sponsorships (legacy)"
