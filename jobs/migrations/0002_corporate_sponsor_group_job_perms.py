"""Give the "Corporate Sponsor" group full CRUD on Job (issue #224).

A member in this group with User.corporation_affiliate set becomes a sponsor
champion and manages job postings for the company they represent (see
jobs.views.JobChampionView). The group previously carried no permissions; this
adds exactly the four Job permissions and leaves its Sponsor grant untouched.

Follows the create_permissions + get_or_create pattern of
core/migrations/0013_executor_group_sponsor_perms.py, and is reversible.
"""

from django.db import migrations

GROUP_NAME = "Corporate Sponsor"
CODENAMES = [
    "add_job",
    "change_job",
    "delete_job",
    "view_job",
]


def grant_perms(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("jobs")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    perms = Permission.objects.filter(content_type__app_label="jobs", codename__in=CODENAMES)
    group.permissions.add(*perms)


def revoke_perms(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        group = Group.objects.get(name=GROUP_NAME)
    except Group.DoesNotExist:
        return
    perms = Permission.objects.filter(content_type__app_label="jobs", codename__in=CODENAMES)
    group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant_perms, revoke_perms),
    ]
