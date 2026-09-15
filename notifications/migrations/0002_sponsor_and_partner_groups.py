"""Provision the "Sponsors" and "Community Partners" membership groups.

Like Ambassadors and the Leadership Council, these carry no permissions of
their own — they record who someone is, so `notifications.models` can gate on
membership. Granted by hand in the admin; nothing to sync from.
"""

from django.db import migrations

from notifications.models import COMMUNITY_PARTNER_GROUP_NAME, SPONSOR_GROUP_NAME

GROUP_NAMES = [SPONSOR_GROUP_NAME, COMMUNITY_PARTNER_GROUP_NAME]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
