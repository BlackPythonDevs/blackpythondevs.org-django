"""Provision the corporate-sponsorship role groups (issue #203).

- "Corporate Sponsorship Coordinator": full CRUD on Sponsor and nothing else,
  so it opens the corporate console but not the event-sponsorship one.
- "Corporate Sponsor": no model permissions. It marks a member who represents
  a sponsor company; with User.corporation_affiliate set it grants the
  read-only /corporate-sponsors/mine/ page. Deliberately separate from the
  notifications "Sponsors" group, which grants notification sending.

get_or_create, so a database that already has either group keeps it.
"""

from django.db import migrations

COORDINATOR_GROUP_NAME = "Corporate Sponsorship Coordinator"
SPONSOR_GROUP_NAME = "Corporate Sponsor"
CODENAMES = ["view_sponsor", "add_sponsor", "change_sponsor", "delete_sponsor"]


def create_groups(apps, schema_editor):
    # Model permissions are normally created by post_migrate, which has not
    # fired yet on a fresh database, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("corporate_sponsorships")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    coordinator, _ = Group.objects.get_or_create(name=COORDINATOR_GROUP_NAME)
    perms = Permission.objects.filter(content_type__app_label="corporate_sponsorships", codename__in=CODENAMES)
    coordinator.permissions.add(*perms)
    Group.objects.get_or_create(name=SPONSOR_GROUP_NAME)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=[COORDINATOR_GROUP_NAME, SPONSOR_GROUP_NAME]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("corporate_sponsorships", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
