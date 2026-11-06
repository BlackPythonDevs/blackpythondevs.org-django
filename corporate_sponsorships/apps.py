from django.apps import AppConfig


class CorporateSponsorshipsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "corporate_sponsorships"
    verbose_name = "Corporate sponsorships"

    def ready(self):
        # Registered here (rather than in checklists) because checklists is
        # a generic app that never imports the models it tracks — see
        # checklists/registry.py.
        from checklists.registry import register

        from .models import Sponsor

        register(
            Sponsor,
            [
                "Contract sent",
                "Contract signed",
                "Invoice sent",
                "Invoice paid",
                "Logo added",
                "Announcement posted",
                "Thank-you sent",
            ],
            name="Corporate sponsor",
        )
