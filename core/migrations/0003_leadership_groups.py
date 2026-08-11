"""Provision the "Leadership Council" and "Leadership" membership groups.

These follow the ambassadors pattern rather than the sponsorships one: they
carry no permissions, they record who someone is. Membership is granted by hand
in the admin — unlike ambassadors there is nothing to sync from, because the
`Leader` snippet is a public roster with no link to a user account.

`get_or_create` keeps this safe to re-run and safe on deployments where someone
has already made the groups by hand.
"""

from django.db import migrations

from core.models import COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME

GROUP_NAMES = [COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
