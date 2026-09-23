"""Create or update an election cycle.

The whole point of splitting `Election` out from a Wagtail page: opening a
new cycle is one command, not a rebuilt page. Idempotent like
`bootstrap_site` — rerunning with corrected dates updates the existing row
for that year instead of duplicating it.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from elections.models import Election

WINDOW_ARGS = ["nomination_opens", "nomination_closes", "voting_opens", "voting_closes"]


def _parse_aware_datetime(name, raw):
    value = parse_datetime(raw)
    if value is None:
        raise CommandError(f"--{name.replace('_', '-')} must be an ISO 8601 datetime, got {raw!r}")
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


class Command(BaseCommand):
    help = "Create or update an election's nomination and voting windows."

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        for name in WINDOW_ARGS:
            parser.add_argument(f"--{name.replace('_', '-')}", required=True, help="ISO 8601 datetime")
        parser.add_argument("--intro", default="", help="Optional blurb shown on the election page.")

    @transaction.atomic
    def handle(self, *args, **options):
        dates = {name: _parse_aware_datetime(name, options[name]) for name in WINDOW_ARGS}

        if not (
            dates["nomination_opens"] < dates["nomination_closes"] <= dates["voting_opens"] < dates["voting_closes"]
        ):
            raise CommandError(
                "Windows must run in order: nomination-opens < nomination-closes <= voting-opens < voting-closes."
            )

        election, created = Election.objects.update_or_create(
            year=options["year"],
            defaults={
                "nomination_opens_at": dates["nomination_opens"],
                "nomination_closes_at": dates["nomination_closes"],
                "voting_opens_at": dates["voting_opens"],
                "voting_closes_at": dates["voting_closes"],
                "intro": options["intro"],
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} election {election.year}."))
