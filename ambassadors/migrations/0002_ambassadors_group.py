"""Provision the "Ambassadors" group: the roster of accepted ambassadors.

Unlike the sponsorships "Executor" group, this one carries no admin
permissions — it's a membership group. Applications are synced into and out of
it as they're accepted or moved off accepted (see signals.py).
"""

from django.db import migrations

from ambassadors.models import GROUP_NAME


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ambassadors", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
