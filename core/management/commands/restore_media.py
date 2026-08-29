"""Restore Wagtail image files from `static/images/`.

A database dump carries the `CustomImage` rows but not the uploaded files, so a
restore onto a fresh server leaves every blog and event header image pointing at
a `/media/...` path with nothing behind it. The originals are checked into
`static/images/` — this copies them back into media storage under the exact
names the database already records, so no rows need rewriting.

    python manage.py restore_media --dry-run
    python manage.py restore_media

Idempotent: images whose file is already in storage are left alone.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import CustomImage, CustomRendition

# Storage appends a 7-character suffix when a name collides, so the file
# recorded as `banner_ariane_ScCmnqU.webp` came from `banner_ariane.webp`.
UPLOAD_SUFFIX_RE = re.compile(r"_[A-Za-z0-9]{7}$")


class Command(BaseCommand):
    help = "Copy Wagtail image originals from static/images into media storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=None,
            help="Directory holding the original files (default: <STATICFILES_DIRS[0]>/images).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report what would be copied.")

    @transaction.atomic
    def handle(self, *args, **options):
        source = Path(options["source"]) if options["source"] else Path(settings.STATICFILES_DIRS[0]) / "images"
        dry_run = options["dry_run"]

        if not source.is_dir():
            self.stderr.write(self.style.ERROR(f"Source directory not found: {source}"))
            return

        # Matched case-insensitively as a fallback: the Jekyll export mixed
        # `BPD_STACKED_featured.png` with lowercase siblings.
        by_name = {path.name: path for path in source.iterdir() if path.is_file()}
        by_lower = {name.lower(): path for name, path in by_name.items()}

        restored, present, missing = 0, 0, []

        for image in CustomImage.objects.order_by("file"):
            if image.file.storage.exists(image.file.name):
                present += 1
                continue

            origin = self.find_source(Path(image.file.name).name, by_name, by_lower)
            if origin is None:
                missing.append(image)
                continue

            self.stdout.write(f"{origin.name} → {image.file.name}")
            if not dry_run:
                self.restore(image, origin)
            restored += 1

        for image in missing:
            self.stderr.write(self.style.WARNING(f"No source for {image.file.name} (image {image.pk}: {image.title})"))

        verb = "would restore" if dry_run else "restored"
        self.stdout.write(self.style.SUCCESS(f"{verb} {restored}, already present {present}, unmatched {len(missing)}"))

    def find_source(self, name, by_name, by_lower):
        stem, _, ext = name.rpartition(".")
        candidates = [name]
        if UPLOAD_SUFFIX_RE.search(stem):
            candidates.append(f"{UPLOAD_SUFFIX_RE.sub('', stem)}.{ext}")
        for candidate in candidates:
            if candidate in by_name:
                return by_name[candidate]
            if candidate.lower() in by_lower:
                return by_lower[candidate.lower()]
        return None

    def restore(self, image, origin):
        storage = image.file.storage
        with origin.open("rb") as fh:
            saved = storage.save(image.file.name, File(fh))

        # storage.save() only picks a different name if something raced us to
        # the path; keep the row honest if it did.
        if saved != image.file.name:
            image.file.name = saved

        # The checked-in original may not be byte-identical to what was uploaded
        # (a re-export, a re-compress), and a stale hash breaks deduplication.
        image.file_size = image.file.size
        image._set_file_hash()
        image.save(update_fields=["file", "file_size", "file_hash"])

        # Renditions were generated from the file that is gone. Deleting the
        # rows makes Wagtail regenerate them on the next request; leaving them
        # would keep serving URLs with nothing behind them.
        CustomRendition.objects.filter(image=image).delete()
