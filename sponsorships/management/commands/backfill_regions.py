"""Recompute the grouping `region` (continent) from each row's `country`.

`region` is normally derived on save() from the country's continent, but rows
imported before the country field existed have a region set with no country to
back it. This command re-derives region from country wherever a country is
present, and reports the rows that still have no country so someone can fill
them in (country is now required on the form, but legacy rows may predate it).

    python manage.py backfill_regions          # apply changes
    python manage.py backfill_regions --dry-run # report only, change nothing
"""

from django.core.management.base import BaseCommand

from sponsorships.models import SponsorshipRequest
from sponsorships.regions import region_for_country


class Command(BaseCommand):
    help = "Re-derive the region (continent) for sponsorship requests from their country."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        updated = 0
        unchanged = 0
        missing_country = []
        unmappable = []

        for req in SponsorshipRequest.objects.all().order_by("name"):
            code = req.country.code if req.country else ""
            if not code:
                missing_country.append(req)
                continue

            region = region_for_country(code)
            if not region:
                unmappable.append(req)
                continue

            if region == req.region:
                unchanged += 1
                continue

            self.stdout.write(f"  {req.name}: {req.region or '(blank)'} → {region}")
            if not dry_run:
                req.region = region
                req.save(update_fields=["region"])
            updated += 1

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} row(s); {unchanged} already correct."))

        if unmappable:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(unmappable)} row(s) have a country with no continent mapping "
                    "(e.g. Antarctica); left unchanged:"
                )
            )
            for req in unmappable:
                self.stdout.write(f"  - {req.name} ({req.country.code})")

        if missing_country:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(missing_country)} row(s) have no country and need one entered manually "
                    "(country is now required on new/edited records):"
                )
            )
            for req in missing_country:
                self.stdout.write(f"  - {req.name} (region: {req.region or 'blank'})")
