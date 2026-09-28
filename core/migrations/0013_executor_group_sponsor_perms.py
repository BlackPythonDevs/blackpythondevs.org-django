"""Give the "Executor" group full CRUD on Sponsor.

Sponsor moved from a Wagtail snippet (edited in /cms/) to its own neapolitan
console at /sponsors/ (core.views.SponsorView) — same shape as
sponsorships/migrations/0003_executor_group.py, which did this for
SponsorshipRequest. get_or_create the group rather than assuming it exists
yet, since core's migrations can run before or after sponsorships'.
"""

from django.db import migrations

GROUP_NAME = "Executor"
CODENAMES = [
    "add_sponsor",
    "change_sponsor",
    "delete_sponsor",
    "view_sponsor",
]


def create_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("core")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    perms = Permission.objects.filter(content_type__app_label="core", codename__in=CODENAMES)
    group.permissions.add(*perms)


def remove_perms(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        group = Group.objects.get(name=GROUP_NAME)
    except Group.DoesNotExist:
        return
    perms = Permission.objects.filter(content_type__app_label="core", codename__in=CODENAMES)
    group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_sponsor_contract_amount_sponsor_expires_at_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_perms),
    ]
