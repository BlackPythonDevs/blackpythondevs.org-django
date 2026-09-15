"""Provision the "Community Admins" group with view/change on Community.

Deliberately narrower than Executor's full CRUD on SponsorshipRequest: a
community admin can update their own community's info but never delete a
Community outright (that stays staff-only, in the Django admin) — see
communities/views.py's CommunityAdminConsole, which only wires up the
list/detail/update roles in the first place.
"""

from django.db import migrations

GROUP_NAME = "Community Admins"
CODENAMES = [
    "view_community",
    "change_community",
]


def create_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("communities")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    perms = Permission.objects.filter(content_type__app_label="communities", codename__in=CODENAMES)
    group.permissions.add(*perms)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("communities", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
