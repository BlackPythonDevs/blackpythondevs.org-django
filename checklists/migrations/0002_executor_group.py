"""Give the "Executor" group full CRUD on checklist Tasks and Notes.

Same shape as sponsorships/migrations/0003_executor_group.py: get_or_create
the group (it may already exist, provisioned by sponsorships) rather than
assuming this migration runs first, and add the four CRUD perms per model.
"""

from django.db import migrations

GROUP_NAME = "Executor"
CODENAMES = [
    "add_task",
    "change_task",
    "delete_task",
    "view_task",
    "add_note",
    "change_note",
    "delete_note",
    "view_note",
]


def create_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("checklists")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    perms = Permission.objects.filter(content_type__app_label="checklists", codename__in=CODENAMES)
    group.permissions.add(*perms)


def remove_perms(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        group = Group.objects.get(name=GROUP_NAME)
    except Group.DoesNotExist:
        return
    perms = Permission.objects.filter(content_type__app_label="checklists", codename__in=CODENAMES)
    group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("checklists", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_perms),
    ]
