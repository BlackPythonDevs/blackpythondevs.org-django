"""Give the "Leadership Council" and "Executor" groups full CRUD on Meeting.

Meetings are a leadership-only console (meetings.views.MeetingView) — unlike
the sponsors one, both leadership groups run it, matching the is_leadership_or_above
tier used by the command center card that links here. get_or_create the
groups rather than assuming they exist yet, mirroring
core/migrations/0013_executor_group_sponsor_perms.py.
"""

from django.db import migrations

GROUP_NAMES = ["Leadership Council", "Executor"]
CODENAMES = [
    "add_meeting",
    "change_meeting",
    "delete_meeting",
    "view_meeting",
]


def create_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("meetings")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name="Executor")
    perms = Permission.objects.filter(content_type__app_label="meetings", codename__in=CODENAMES)
    group.permissions.add(*perms)

    group, _ = Group.objects.get_or_create(name="Leadership Council")
    group.permissions.add(*perms)


def remove_perms(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    perms = Permission.objects.filter(content_type__app_label="meetings", codename__in=CODENAMES)
    for name in GROUP_NAMES:
        try:
            group = Group.objects.get(name=name)
        except Group.DoesNotExist:
            continue
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("meetings", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_perms),
    ]
