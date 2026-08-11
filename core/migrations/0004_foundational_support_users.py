"""Move foundational supporters from bare names onto user accounts.

Every existing supporter name becomes an unverified placeholder account (see
`core.supporters`) plus a `FoundationalSupport` row recording the year and
status, so someone who gave across several years is one identity with a
history. Reversing collapses the rows back to names and leaves the placeholder
accounts alone — deleting accounts on a rollback would be the destructive
choice.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.supporters import get_or_create_supporter_user


def link_to_users(apps, schema_editor):
    Supporter = apps.get_model("core", "FoundationalSupporter")
    Support = apps.get_model("core", "FoundationalSupport")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    for supporter in Supporter.objects.all():
        user, _ = get_or_create_supporter_user(User, supporter.name)
        Support.objects.get_or_create(user=user, year=supporter.year, defaults={"status": "listed"})


def unlink_from_users(apps, schema_editor):
    Supporter = apps.get_model("core", "FoundationalSupporter")
    Support = apps.get_model("core", "FoundationalSupport")

    for entry in Support.objects.select_related("user"):
        name = entry.user.display_name or entry.user.username
        Supporter.objects.get_or_create(name=name, year=entry.year)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_leadership_groups'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FoundationalSupport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField(db_index=True)),
                ('status', models.CharField(choices=[('listed', 'Listed publicly'), ('anonymous', 'Anonymous'), ('pending', 'Pending confirmation')], default='listed', help_text="Only 'Listed publicly' appears on the support page.", max_length=20)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='foundational_support', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'foundational support',
                'verbose_name_plural': 'foundational support',
                'ordering': ['-year', 'user__display_name'],
                'unique_together': {('user', 'year')},
            },
        ),
        migrations.RunPython(link_to_users, unlink_from_users),
        migrations.DeleteModel(
            name='FoundationalSupporter',
        ),
    ]
