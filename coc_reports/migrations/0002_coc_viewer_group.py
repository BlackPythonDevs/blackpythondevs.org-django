"""Provision the "COC Report Viewing" group with view + change on CoC reports.

Superusers already have every permission; this migration gives the COC Report
Viewing role view and change on CocReport — and deliberately nothing else. No
add (reports are made on the website's public form, which is what captures the
reporter and seeds the checklist) and no delete (a report cannot be un-created
once filed — see coc_reports.models.CocReport).
"""

from django.db import migrations

GROUP_NAME = "COC Report Viewing"
CODENAMES = [
    "change_cocreport",
    "view_cocreport",
]


def create_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("coc_reports")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    perms = Permission.objects.filter(content_type__app_label="coc_reports", codename__in=CODENAMES)
    group.permissions.add(*perms)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("coc_reports", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
