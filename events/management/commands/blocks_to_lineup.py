"""Move summit speakers and schedules out of body blocks and into the page.

Speakers and schedules were briefly StreamField blocks. They're now inline
children of the summit page, so a speaker is entered once as a `core.Speaker`
snippet and the schedule points at it instead of repeating the name as text.

This lifts the existing block data across: each speaker becomes a snippet
(matched on name, so someone appearing at two summits stays one record), each
schedule row becomes a `SummitScheduleItem` with its presenter resolved to a
snippet where the name matches. The blocks are then dropped from the body.

Idempotent: pages whose body holds no speaker or schedule blocks are skipped,
so re-running after a partial run is safe. Dry-run by default.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Speaker
from events.models import LeadershipSummitPage, SummitScheduleItem, SummitSpeaker

CONVERTED_BLOCKS = {"speakers", "schedule"}


class Command(BaseCommand):
    help = "Convert speaker/schedule body blocks into inline page children."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the changes.")

    def handle(self, *args, **options):
        pages = [p for p in LeadershipSummitPage.objects.all() if self.blocks_of(p)]
        if not pages:
            self.stdout.write("No speaker or schedule blocks left to convert.")
            return

        for page in pages:
            kinds = [b.block_type for b in self.blocks_of(page)]
            self.stdout.write(f"{page.pk}: {page.title} — {len(kinds)} block(s): {', '.join(kinds)}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nDry run. Re-run with --apply to convert."))
            return

        for page in pages:
            self.convert(page)
        self.stdout.write(self.style.SUCCESS(f"Converted {len(pages)} page(s)."))

    def blocks_of(self, page):
        return [b for b in page.body if b.block_type in CONVERTED_BLOCKS]

    def speaker_snippet(self, data):
        """Find or create the snippet for one speaker block entry.

        Matched on name: the same person speaking at two summits should be one
        snippet, not two. An existing record keeps its bio and photo rather than
        being overwritten by whichever page is converted last.
        """
        speaker, created = Speaker.objects.get_or_create(
            name=data["name"],
            defaults={
                "url": data.get("url") or "",
                "photo_url": data.get("photo_url") or "",
                "bio": data.get("bio") or "",
            },
        )
        if created and data.get("photo"):
            speaker.photo = data["photo"]
            speaker.save(update_fields=["photo"])
        return speaker

    @transaction.atomic
    def convert(self, page):
        by_name = {}
        speaker_order = schedule_order = 0

        for block in page.body:
            if block.block_type == "speakers":
                heading = block.value.get("heading") or "Speakers"
                for entry in block.value["speakers"]:
                    speaker = self.speaker_snippet(entry)
                    by_name[speaker.name] = speaker
                    SummitSpeaker.objects.create(
                        page=page,
                        speaker=speaker,
                        group=heading,
                        talk_title=entry.get("talk_title") or "",
                        sort_order=speaker_order,
                    )
                    speaker_order += 1
            elif block.block_type == "schedule":
                track = block.value.get("heading") or ""
                for item in block.value["items"]:
                    presenter = item.get("presenter") or ""
                    # Resolve the free-text presenter to a snippet where it names
                    # someone in the line-up; anything else stays as text.
                    speaker = by_name.get(presenter) or Speaker.objects.filter(name=presenter).first()
                    SummitScheduleItem.objects.create(
                        page=page,
                        track=track,
                        time=item["time"],
                        title=item["title"],
                        speaker=speaker,
                        presenter="" if speaker else presenter,
                        sort_order=schedule_order,
                    )
                    schedule_order += 1

        page.body = [(b.block_type, b.value) for b in page.body if b.block_type not in CONVERTED_BLOCKS]
        page.save()
        page.save_revision().publish()
        self.stdout.write(
            f"Converted {page.pk}: {page.speaker_lineup.count()} speaker(s), "
            f"{page.schedule_items.count()} schedule row(s)"
        )
