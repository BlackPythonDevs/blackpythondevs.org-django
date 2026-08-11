from django.apps import AppConfig


class AmbassadorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ambassadors"
    verbose_name = "Student Ambassadors"

    def ready(self):
        # Wire up the group-membership sync (see signals.py).
        from . import signals  # noqa: F401
