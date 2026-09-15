from django.apps import AppConfig


class CommunitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "communities"

    def ready(self):
        # Wire up the "Community Admins" group-membership sync (see signals.py).
        from . import signals  # noqa: F401
