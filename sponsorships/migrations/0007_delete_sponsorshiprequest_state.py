"""SponsorshipRequest now lives in event_sponsorships (issue #202).

State only: the table keeps its name, sponsorships_sponsorshiprequest, and now
belongs to event_sponsorships.SponsorshipRequest (see that app's 0001; its
0002 relabels the content type first). Nothing in the database is dropped.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sponsorships", "0006_sponsorshiprequest_contact_email_and_more"),
        ("event_sponsorships", "0002_relabel_content_type"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="SponsorshipRequest")],
            database_operations=[],
        ),
    ]
