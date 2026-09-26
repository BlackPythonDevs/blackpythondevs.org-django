"""Provision the "Student" membership group.

Follows the same pattern as the Leadership/Ambassadors groups: it carries no
permissions, it just records who someone is, so views and templates can gate
on it. Membership is granted by hand in the admin.

`get_or_create` keeps this safe to re-run and safe on deployments where
someone has already made the group by hand.
"""

from django.db import migrations

from core.models import STUDENT_GROUP_NAME

GROUP_NAMES = [STUDENT_GROUP_NAME]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_consolidate_leadership_groups"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
