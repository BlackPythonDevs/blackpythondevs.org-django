"""Seed default checklist tasks for rows that predate their model's
registration (see checklists/registry.py) — the post_save hook only fires
for rows created after `register()` ran.

    python manage.py backfill_checklists            # apply
    python manage.py backfill_checklists --dry-run  # report only
"""

from django.core.management.base import BaseCommand

from checklists import registry
from checklists.models import Task


class Command(BaseCommand):
    help = "Seed default Task rows for existing objects of every registered checklist model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        from django.contrib.contenttypes.models import ContentType

        total_seeded = 0
        for definition in registry.definitions():
            model = definition["model"]
            content_type = ContentType.objects.get_for_model(model)
            already = set(
                Task.objects.filter(content_type=content_type).values_list("object_id", flat=True).distinct()
            )
            missing = model._default_manager.exclude(pk__in=already)
            count = missing.count()
            if count:
                self.stdout.write(f"{definition['name']}: {count} object(s) with no checklist yet")
            for obj in missing:
                if not dry_run:
                    registry.seed_defaults(obj)
                total_seeded += 1

        verb = "Would seed" if dry_run else "Seeded"
        self.stdout.write(self.style.SUCCESS(f"{verb} checklists for {total_seeded} object(s)."))
