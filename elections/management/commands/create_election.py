"""Create or update an election cycle.

The whole point of splitting `Election` out from a Wagtail page: opening a
new cycle is one command, not a rebuilt page. Idempotent like
`bootstrap_site` — rerunning with corrected dates updates the existing row
for that year instead of duplicating it.

Windows are given as plain dates, not datetimes — see
`elections.models.aoe_instant` for why: every boundary (both opens and
closes) is anchored to AOE ("Anywhere on Earth", UTC-12), the standard
deadline convention. A window opens once its date has begun everywhere on
Earth and closes once its date has ended everywhere on Earth, so nobody's
local clock excludes them for being "too early" or "too late".
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from elections.models import Election, aoe_instant, default_election_year

WINDOW_ARGS = ["nomination_opens", "nomination_closes", "voting_opens", "voting_closes"]
ONE_DAY = datetime.timedelta(days=1)


def _parse_date(name, raw):
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError as exc:
        raise CommandError(f"--{name.replace('_', '-')} must be a date (YYYY-MM-DD), got {raw!r}") from exc


class Command(BaseCommand):
    help = "Create or update an election's nomination and voting windows (dates, AOE)."

    def add_arguments(self, parser):
        parser.add_argument(
            "year", type=int, nargs="?", default=None, help="Defaults to next calendar year if omitted."
        )
        for name in WINDOW_ARGS:
            parser.add_argument(f"--{name.replace('_', '-')}", required=True, help="Date (YYYY-MM-DD), AOE")
        parser.add_argument("--intro", default="", help="Optional blurb shown on the election page.")

    @transaction.atomic
    def handle(self, *args, **options):
        year = options["year"] if options["year"] is not None else default_election_year()
        dates = {name: _parse_date(name, options[name]) for name in WINDOW_ARGS}

        # Opens: the instant that date begins, AOE. Closes: the instant the
        # *next* date begins, AOE — i.e. the moment that date has ended.
        instants = {
            "nomination_opens": aoe_instant(dates["nomination_opens"]),
            "nomination_closes": aoe_instant(dates["nomination_closes"] + ONE_DAY),
            "voting_opens": aoe_instant(dates["voting_opens"]),
            "voting_closes": aoe_instant(dates["voting_closes"] + ONE_DAY),
        }

        if instants["nomination_opens"] >= instants["nomination_closes"]:
            raise CommandError("--nomination-opens must be before --nomination-closes.")
        if instants["voting_opens"] >= instants["voting_closes"]:
            raise CommandError("--voting-opens must be before --voting-closes.")
        if instants["voting_opens"] < instants["nomination_closes"]:
            raise CommandError("--voting-opens must be on or after --nomination-closes.")

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
