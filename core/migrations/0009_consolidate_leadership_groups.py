"""Fold the "Leadership" group into "Leadership Council".

The two never carried a different set of permissions or gated different
features — every check that cared about one cared about the other
(`core.models.is_leadership_or_above`), and migration 0008 granted them the
same CMS access. The split was a distinction without a difference, so anyone
in "Leadership" moves to "Leadership Council" and the "Leadership" group is
removed.

One-way: once members are merged there's no record of which group they came
from, so this migration doesn't reverse.
"""

from django.db import migrations

from core.models import COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME


def merge_into_council(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    leadership = Group.objects.filter(name=LEADERSHIP_GROUP_NAME).first()
    if leadership is None:
        return
    council, _ = Group.objects.get_or_create(name=COUNCIL_GROUP_NAME)
    for user in leadership.user_set.all():
        user.groups.add(council)
    leadership.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_cms_editor_access"),
    ]

    operations = [
        migrations.RunPython(merge_into_council, migrations.RunPython.noop),
    ]
