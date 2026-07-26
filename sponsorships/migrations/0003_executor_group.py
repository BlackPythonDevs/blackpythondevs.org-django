"""Provision the "Executor" group with full CRUD on sponsorship requests.

Superusers already have every permission; this migration gives the Executor
group add/change/delete/view on SponsorshipRequest so those users (once granted
staff access) can manage records in the Django admin and no one else can.
"""

from django.db import migrations

GROUP_NAME = "Executor"
CODENAMES = [
    "add_sponsorshiprequest",
    "change_sponsorshiprequest",
    "delete_sponsorshiprequest",
    "view_sponsorshiprequest",
]


def create_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("sponsorships")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    perms = Permission.objects.filter(
        content_type__app_label="sponsorships", codename__in=CODENAMES
    )
    group.permissions.add(*perms)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sponsorships", "0002_migrate_sponsored_events"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
