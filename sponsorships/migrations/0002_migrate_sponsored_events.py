"""Copy the existing events.SponsoredEvent rows into the standalone model.

The old records lived as Wagtail Orderables inlined on the single
EventIndexPage. They carry over one-for-one; the parent-page link is dropped
because these are now free-standing records rather than page children.
"""

from django.db import migrations


def copy_forward(apps, schema_editor):
    SponsoredEvent = apps.get_model("events", "SponsoredEvent")
    SponsorshipRequest = apps.get_model("sponsorships", "SponsorshipRequest")

    rows = [
        SponsorshipRequest(
            year=old.year,
            region=old.region,
            name=old.name,
            url=old.url,
            status=old.status,
            paid=old.paid,
            amount=old.amount,
            notes=old.notes,
        )
        for old in SponsoredEvent.objects.all()
    ]
    SponsorshipRequest.objects.bulk_create(rows)


def copy_backward(apps, schema_editor):
    # The old events.SponsoredEvent needs a parent page; reversing the data
    # move is not meaningful, so this is a no-op. Reverse the events-app
    # migration that drops the model separately if you truly need the old table.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("sponsorships", "0001_initial"),
        ("events", "0003_alter_sponsoredevent_options_sponsoredevent_amount_and_more"),
    ]

    operations = [
        migrations.RunPython(copy_forward, copy_backward),
    ]
