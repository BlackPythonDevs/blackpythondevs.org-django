"""Load the foundational supporter roster from a CSV or JSON file.

Built for re-uploading the whole roster since the beginning of BPD: run with
`--replace` and the file becomes the truth, with anything not in it removed.

    python manage.py import_foundational_supporters supporters.csv --replace

CSV wants a header row with `name`, `year`, and ideally `email`; `status` and
`note` are optional. JSON takes either a flat list of the same keys or the
year-keyed shape the original fixture used:

    {"2024": [{"name": "Ada Lovelace", "email": "ada@example.com"}, "Alan Turing"]}

An email makes the account claimable — the supporter signs in with an emailed
code and the account is theirs. Names without one get an unloginable
placeholder, and re-importing them later *with* an address upgrades that same
account, keeping their history.
"""

import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import FoundationalSupport
from core.supporters import import_supporters

VALID_STATUSES = {value for value, _ in FoundationalSupport.STATUS_CHOICES}


def _normalise(record, year=None):
    """Turn one input record into a `{name, email, year, status, note}` dict."""
    if isinstance(record, str):
        record = {"name": record}
    if not isinstance(record, dict):
        raise CommandError(f"Expected a name or an object, got: {record!r}")

    row = {key: (str(record.get(key) or "")).strip() for key in ("name", "email", "status", "note")}
    row["year"] = str(record.get("year") or year or "").strip()

    if not row["name"] and not row["email"]:
        raise CommandError(f"Row needs a name or an email: {record!r}")
    if not row["year"].isdigit():
        raise CommandError(f"Row needs a numeric year, got {row['year']!r}: {record!r}")
    if row["status"] and row["status"] not in VALID_STATUSES:
        raise CommandError(f"Unknown status {row['status']!r}; choose from {sorted(VALID_STATUSES)}")
    return row


def parse_rows(path):
    text = path.read_text()

    if path.suffix.lower() == ".csv":
        return [_normalise(record) for record in csv.DictReader(text.splitlines())]

    data = json.loads(text)
    if isinstance(data, dict):
        # Year-keyed: {"2024": [names or objects]}
        return [_normalise(record, year=year) for year, records in data.items() for record in records]
    return [_normalise(record) for record in data]


class Command(BaseCommand):
    help = "Import foundational supporters from a CSV or JSON file."

    def add_arguments(self, parser):
        parser.add_argument("path", help="CSV or JSON file to import.")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Clear the existing roster first, deleting placeholder accounts left with no support.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report without writing anything.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"No such file: {path}")

        rows = parse_rows(path)
        years = sorted({row["year"] for row in rows})
        without_email = sum(1 for row in rows if not row["email"])
        span = f"across {len(years)} years ({years[0]}–{years[-1]})" if years else ""
        self.stdout.write(f"Parsed {len(rows)} rows {span}.".replace("  ", " "))
        if without_email:
            self.stdout.write(
                self.style.WARNING(f"{without_email} rows have no email; those accounts cannot be claimed.")
            )

        if options["dry_run"]:
            self.stdout.write("Dry run — nothing written.")
            return

        stats = import_supporters(rows, clear=options["replace"])
        if options["replace"]:
            self.stdout.write(
                f"Cleared {stats['support_deleted']} support records "
                f"and {stats['users_deleted']} unclaimed placeholder accounts."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {stats['support']} support records, creating {stats['users_created']} accounts."
            )
        )
