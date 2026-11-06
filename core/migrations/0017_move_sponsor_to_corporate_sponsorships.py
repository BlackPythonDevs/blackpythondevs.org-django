"""Sponsor now lives in corporate_sponsorships (issue #201).

State only: the table keeps its name, core_sponsor, and now belongs to
corporate_sponsorships.Sponsor (see that app's 0001, which also relabels the
content type). Nothing in the database is dropped.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_sponsor_primary_contact_user"),
        ("corporate_sponsorships", "0001_initial"),
        # CustomBlogPage.sponsor must be pointed at the new model before the
        # old one leaves the state.
        ("blog", "0015_alter_customblogpage_sponsor"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Sponsor")],
            database_operations=[],
        ),
    ]
