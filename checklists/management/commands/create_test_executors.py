"""Seed a handful of fake Executor-group accounts for trying out @mentions
(mentions.py) locally without needing real teammates signed up.

    python manage.py create_test_executors

Idempotent: re-running just makes sure they exist and are in the Executor
group, rather than duplicating them. Refuses to run unless DEBUG is on (or
--force is passed) since these are throwaway accounts with a shared,
publicly-known password — never something to create against the real site.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

# (username, email) — this project derives `username` from the email's local
# part at real signup (see users/adapters.py); these are just given directly
# since there's no signup flow to run them through.
TEST_EXECUTORS = [
    ("test_executor_1", "test-executor-1@example.com"),
    ("test_executor_2", "test-executor-2@example.com"),
    ("test_executor_3", "test-executor-3@example.com"),
]

TEST_EXECUTOR_PASSWORD = "test-executor-password"


class Command(BaseCommand):
    help = "Create a handful of fake Executor accounts for testing @mentions locally."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Create them even with DEBUG off. Never do this against the real site.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to create test accounts outside DEBUG. Pass --force to override.")

        group, _ = Group.objects.get_or_create(name="Executor")
        User = get_user_model()

        created = []
        for username, email in TEST_EXECUTORS:
            user, was_created = User.objects.get_or_create(username=username, defaults={"email": email})
            if was_created:
                user.set_password(TEST_EXECUTOR_PASSWORD)
                user.save(update_fields=["password"])
                created.append(username)
            user.groups.add(group)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created: {', '.join(created)}"))
        self.stdout.write(f"All {len(TEST_EXECUTORS)} test executors are in the Executor group.")
        self.stdout.write(f"Password for any created account: {TEST_EXECUTOR_PASSWORD}")
        self.stdout.write("Mention them with: " + " ".join(f"@{username}" for username, _ in TEST_EXECUTORS))
