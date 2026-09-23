"""Create or update an election cycle.

The whole point of splitting `Election` out from a Wagtail page: opening a
new cycle is one command, not a rebuilt page. Idempotent like
`bootstrap_site` — rerunning with corrected dates updates the existing row
for that year instead of duplicating it.

Windows are given as plain dates, not datetimes — see
`elections.models.earliest_utc_instant`/`latest_utc_instant` for why: a
window that *opens* on a date opens at the earliest instant that date exists
anywhere on Earth, and one that *closes* on a date closes at the latest
instant that date is still going anywhere on Earth. That way nobody's local
clock excludes them for being "too early" or "too late".
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from elections.models import Election, default_election_year, earliest_utc_instant, latest_utc_instant

OPENS_ARGS = ["nomination_opens", "voting_opens"]
CLOSES_ARGS = ["nomination_closes", "voting_closes"]


def _parse_date(name, raw):
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError as exc:
        raise CommandError(f"--{name.replace('_', '-')} must be a date (YYYY-MM-DD), got {raw!r}") from exc


class Command(BaseCommand):
    help = "Create or update an election's nomination and voting windows."

    def add_arguments(self, parser):
        parser.add_argument(
            "year", type=int, nargs="?", default=None, help="Defaults to next calendar year if omitted."
        )
        for name in OPENS_ARGS + CLOSES_ARGS:
            parser.add_argument(f"--{name.replace('_', '-')}", required=True, help="Date (YYYY-MM-DD)")
        parser.add_argument("--intro", default="", help="Optional blurb shown on the election page.")

    @transaction.atomic
    def handle(self, *args, **options):
        year = options["year"] if options["year"] is not None else default_election_year()

        dates = {name: _parse_date(name, options[name]) for name in OPENS_ARGS + CLOSES_ARGS}
        instants = {name: earliest_utc_instant(dates[name]) for name in OPENS_ARGS}
        instants.update({name: latest_utc_instant(dates[name]) for name in CLOSES_ARGS})

        if instants["nomination_opens"] >= instants["nomination_closes"]:
            raise CommandError("--nomination-opens must be before --nomination-closes.")
        if instants["voting_opens"] >= instants["voting_closes"]:
            raise CommandError("--voting-opens must be before --voting-closes.")
        if instants["voting_opens"] < instants["nomination_closes"]:
            # Expected when the two dates are adjacent or the same: nominations
            # only truly close once the last timezone on Earth finishes that
            # date, while voting opens as soon as the first timezone reaches
            # its date — those two instants can overlap by design.
            self.stdout.write(self.style.WARNING("Note: the nomination and voting windows overlap given these dates."))

        election, created = Election.objects.update_or_create(
            year=year,
            defaults={
                "nomination_opens_at": instants["nomination_opens"],
                "nomination_closes_at": instants["nomination_closes"],
                "voting_opens_at": instants["voting_opens"],
                "voting_closes_at": instants["voting_closes"],
                "intro": options["intro"],
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} election {election.year}."))
