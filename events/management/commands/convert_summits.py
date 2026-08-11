"""Convert existing EventPages into LeadershipSummitPages.

The summit page type arrived after the summit pages did, so pages imported from
the old site are plain ``EventPage`` rows and still edit with the generic event
form (start date *and* end date, no host-conference fields). This retypes them.

Wagtail has no built-in "change page type", so the conversion does what Django's
multi-table inheritance requires by hand: insert the child row keyed to the
existing page, then repoint the page's content type. The page keeps its id, path,
slug, url, and revision history — only its type changes.

Run it with ``--dry-run`` first; nothing is written without ``--apply``.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from events.models import EventPage, LeadershipSummitPage


class Command(BaseCommand):
    help = "Retype Leadership Summit EventPages as LeadershipSummitPages."

    def add_arguments(self, parser):
        parser.add_argument(
            "slugs",
            nargs="*",
            help="Page slugs to convert. Defaults to every EventPage whose title contains 'Summit'.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually convert. Without this the command only reports what it would do.",
        )

    def handle(self, *args, **options):
        pages = self.find_pages(options["slugs"])
        if not pages:
            self.stdout.write("No EventPages to convert.")
            return

        for page in pages:
            blocks = len(page.body)
            note = f" — has {blocks} body block(s), which will render below the generated sections" if blocks else ""
            self.stdout.write(f"{page.pk}: {page.title} ({page.slug}){note}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nDry run. Re-run with --apply to convert."))
            return

        for page in pages:
            self.convert(page)
        self.stdout.write(self.style.SUCCESS(f"Converted {len(pages)} page(s)."))

    def find_pages(self, slugs):
        """EventPages that are not already summits."""
        summit_ids = LeadershipSummitPage.objects.values_list("eventpage_ptr_id", flat=True)
        pages = EventPage.objects.exclude(pk__in=summit_ids)
        if slugs:
            return list(pages.filter(slug__in=slugs))
        return list(pages.filter(title__icontains="summit"))

    @transaction.atomic
    def convert(self, page):
        # The child row carries only the summit-specific columns; everything
        # else already lives in the eventpage/page rows it points at. `raw=True`
        # is what keeps Django from re-saving those parent rows.
        summit = LeadershipSummitPage(eventpage_ptr_id=page.pk)
        summit.save_base(raw=True, force_insert=True)

        # Point the page at its new type so Wagtail loads the new panels and
        # template. `.specific` and the edit view both read this.
        content_type = ContentType.objects.get_for_model(LeadershipSummitPage)
        EventPage.objects.filter(pk=page.pk).update(content_type=content_type)

        # Publish a revision of the now-correctly-typed page, so the editor
        # doesn't open a stale EventPage-shaped revision. This also runs
        # LeadershipSummitPage.save(), which mirrors end_date onto the one date.
        summit = LeadershipSummitPage.objects.get(pk=page.pk)
        summit.save()
        summit.save_revision().publish()
        self.stdout.write(f"Converted {page.pk}: {page.title}")
