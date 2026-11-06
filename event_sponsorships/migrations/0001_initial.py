"""Move SponsorshipRequest from sponsorships into this app without touching its table (issue #202).

State only: the model keeps db_table="sponsorships_sponsorshiprequest", so no
table or row is renamed and a deploy can briefly run new code against the old
schema. 0002 relabels the content type; sponsorships 0007 then deletes the old
state copy of the model.
"""

import django.db.models.deletion
import django_countries.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sponsorships", "0006_sponsorshiprequest_contact_email_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="SponsorshipRequest",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("year", models.PositiveIntegerField(db_index=True, editable=False)),
                        ("region", models.CharField(blank=True, editable=False, max_length=80)),
                        ("name", models.CharField(max_length=200)),
                        ("url", models.URLField(blank=True, help_text="The event's website.")),
                        ("status", models.CharField(choices=[("requested", "Requested"), ("approved", "Approved"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="requested", help_text="Only completed sponsorships appear on the public events page.", max_length=20)),
                        ("paid", models.BooleanField(default=True, help_text="Tick when Black Python Devs transferred funds. Leave unticked for community sponsorships contributed as visibility, volunteer time, or other non-monetary support.")),
                        ("amount_requested", models.DecimalField(blank=True, decimal_places=2, help_text="Amount the event asked for, for internal records. Never shown on the public site.", max_digits=10, null=True)),
                        ("notes", models.TextField(blank=True, help_text="Internal notes. Not shown publicly.")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("country", django_countries.fields.CountryField(help_text="Event country. The public listing groups by the country's region.", max_length=2)),
                        ("prospectus_url", models.URLField(blank=True, help_text="Link to the event's sponsorship prospectus.")),
                        ("start_date", models.DateField(help_text="Event start date. The year shown on the public site is taken from this.", null=True)),
                        ("contact_email", models.EmailField(blank=True, help_text="Best contact email for this request.", max_length=254)),
                        ("contact_name", models.CharField(blank=True, help_text="The person to contact about this request.", max_length=200)),
                        ("contact_user", models.ForeignKey(blank=True, help_text="The member matching the contact email, if they already have an account.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sponsorship_requests_contact", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "verbose_name": "sponsorship request",
                        "verbose_name_plural": "sponsorship requests",
                        "ordering": ["-year", "region", "name"],
                        "db_table": "sponsorships_sponsorshiprequest",
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
