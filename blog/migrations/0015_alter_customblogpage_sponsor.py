"""Point CustomBlogPage.sponsor at corporate_sponsorships.Sponsor (issue #201).

State only: the model kept its table (core_sponsor), so the existing foreign
key constraint is already correct.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0014_alter_blogpage_body"),
        ("corporate_sponsorships", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="customblogpage",
                    name="sponsor",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="announcement_posts", to="corporate_sponsorships.sponsor"),
                ),
            ],
            database_operations=[],
        ),
    ]
