"""Provision the "Onboarding Team" membership group.

Same shape as 0003_leadership_groups.py: no permissions of its own, just
records who's on the team that turns a newly-accepted council member's
draft announcement + profile photo into the social media post. Membership
is granted by hand in the admin.
"""

from django.db import migrations

from core.models import ONBOARDING_GROUP_NAME


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ONBOARDING_GROUP_NAME)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=ONBOARDING_GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_student_group"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
