from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    """Generic follow-through checklists + notes, attachable to any model.

    This app never imports the models it tracks — see registry.py. Other
    apps opt a model in from their own AppConfig.ready(), e.g. core's does
    it for Sponsor.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "checklists"
    verbose_name = "Checklists"
