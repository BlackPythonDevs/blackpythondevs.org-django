from django.apps import AppConfig


class EventSponsorshipsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "event_sponsorships"
    verbose_name = "Event sponsorships"

    def ready(self):
        # Registered here (rather than in checklists) because checklists is
        # a generic app that never imports the models it tracks — see
        # checklists/registry.py.
        from checklists.registry import register

        from .models import SponsorshipRequest

        register(
            SponsorshipRequest,
            [
                "Prospectus reviewed",
                "Approved",
                "Funds transferred",
                "Event completed",
                "Added to public events page",
            ],
            name="Event sponsorship",
        )
