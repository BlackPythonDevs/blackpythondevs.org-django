"""Create or update an election cycle.

Windows are given as plain dates, not datetimes — see
`elections.models.opens_instant`/`closes_instant` for why: a window opens
once its date has begun ANYWHERE on Earth (the first timezone, UTC+14) and
closes once its date has ended ANYWHERE on Earth (AOE, the last timezone,
UTC-12), so nobody's local clock excludes them for being "too early" or "too
late".

The Django admin's "add election" form
(`elections.forms.ElectionAdminForm`) takes the same four dates and
validates them the same way, via `elections.models.election_window_instants`.
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from elections.models import Election, default_election_year, election_window_instants

WINDOW_ARGS = ["nomination_opens", "nomination_closes", "voting_opens", "voting_closes"]


def _parse_date(name, raw):
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError as exc:
        raise CommandError(
            f"--{name.replace('_', '-')} must be a date (YYYY-MM-DD), got {raw!r}"
        ) from exc


class Command(BaseCommand):
    help = "Create or update an election's nomination and voting windows (dates)."

    def add_arguments(self, parser):
        parser.add_argument(
            "year",
            type=int,
            nargs="?",
            default=None,
            help="Defaults to next calendar year if omitted.",
        )
        parser.add_argument(
            "--nomination-opens",
            required=True,
            help="Date (YYYY-MM-DD) — begins anywhere.",
        )
        parser.add_argument(
            "--nomination-closes",
            required=True,
            help="Date (YYYY-MM-DD), AOE — ends everywhere.",
        )
        parser.add_argument(
            "--voting-opens", required=True, help="Date (YYYY-MM-DD) — begins anywhere."
        )
        parser.add_argument(
            "--voting-closes",
            required=True,
            help="Date (YYYY-MM-DD), AOE — ends everywhere.",
        )
        parser.add_argument(
            "--intro", default="", help="Optional blurb shown on the election page."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        year = (
            options["year"] if options["year"] is not None else default_election_year()
        )
        dates = {name: _parse_date(name, options[name]) for name in WINDOW_ARGS}

        instants, errors = election_window_instants(
            *(dates[name] for name in WINDOW_ARGS)
        )
        if errors:
            raise CommandError(
                " ".join(
                    f"--{name.replace('_', '-')}: {message}"
                    for name, message in errors.items()
                )
            )
        if instants["voting_opens"] < instants["nomination_closes"]:
            # Expected, not a mistake: opens use the earliest timezone and
            # closes use the latest, so adjacent dates overlap by design —
            # see the note on elections.models.election_window_instants.
            self.stdout.write(
                self.style.WARNING(
                    "Note: the nomination and voting windows overlap given these dates. Leave a couple of "
                    "days between --nomination-closes and --voting-opens if you want a clean handoff instead."
                )
            )

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
