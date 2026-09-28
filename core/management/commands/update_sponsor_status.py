"""Transition Sponsor.status as each sponsor's contract term nears or reaches
its end.

Only rows with an invoice_paid_date (and so a derived expires_at) are
touched — a sponsor with no recorded invoice date never auto-expires, since
there's nothing to measure the term against.

Reaching STATUS_EXPIRED also clears the public `active` flag, so the
homepage sponsor strip drops the sponsor without anyone editing it by hand.
Renewing a sponsor (recording a new invoice_paid_date, which pushes
expires_at into the future) is expected to move status back to `active` and
re-tick `active` as part of that edit — this command only ever moves a
sponsor forward towards expiry, never back.

    python manage.py update_sponsor_status           # apply changes
    python manage.py update_sponsor_status --dry-run  # report only
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Sponsor

EXPIRING_SOON_WINDOW = timedelta(days=30)


class Command(BaseCommand):
    help = "Move Sponsor.status to expiring_soon/expired based on expires_at."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today = timezone.localdate()

        expiring_soon = 0
        expired = 0

        sponsors = Sponsor.objects.filter(
            expires_at__isnull=False,
            status__in=[Sponsor.STATUS_ACTIVE, Sponsor.STATUS_EXPIRING_SOON],
        ).order_by("expires_at")

        for sponsor in sponsors:
            if sponsor.expires_at <= today:
                self.stdout.write(f"  {sponsor.name}: {sponsor.status} → expired (expired {sponsor.expires_at})")
                if not dry_run:
                    sponsor.status = Sponsor.STATUS_EXPIRED
                    sponsor.active = False
                    sponsor.save(update_fields=["status", "active"])
                expired += 1
            elif sponsor.status == Sponsor.STATUS_ACTIVE and sponsor.expires_at - today <= EXPIRING_SOON_WINDOW:
                self.stdout.write(f"  {sponsor.name}: active → expiring_soon (expires {sponsor.expires_at})")
                if not dry_run:
                    sponsor.status = Sponsor.STATUS_EXPIRING_SOON
                    sponsor.save(update_fields=["status"])
                expiring_soon += 1

        verb = "Would move" if dry_run else "Moved"
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"{verb} {expiring_soon} sponsor(s) to expiring_soon, {expired} to expired.")
        )
