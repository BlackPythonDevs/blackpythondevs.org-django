"""Delete the django-auditlog entries recorded for ballots and their rankings
before they were excluded from auditing (see AUDITLOG_EXCLUDE_TRACKING_MODELS
and `elections.models.Ballot`).

Each of those entries records the voter as its actor (with their email and
IP) and the ballot's token in its changes. The token is still on the ballot,
so the entry ties a voter to their rankings. Entries are deleted rather than
redacted: even a redacted "ballot created" entry keeps a timestamp that
matches the voter's VoteRecord entry to the millisecond.

Only entries about `elections.Ballot` and `elections.BallotRanking` are
touched. VoteRecord entries (who voted, not how), all other audit history,
and the ballots themselves are left alone, so the tally can't change.

Irreversible by nature: unapplying this migration restores nothing.
"""

from django.db import migrations

BALLOT_MODELS = ("ballot", "ballotranking")


def scrub_ballot_audit_entries(apps, schema_editor):
    LogEntry = apps.get_model("auditlog", "LogEntry")
    entries = LogEntry.objects.filter(content_type__app_label="elections", content_type__model__in=BALLOT_MODELS)
    deleted, _ = entries.delete()
    if deleted:
        print(f"\n  Deleted {deleted} audit log entries for ballots and ballot rankings.")


class Migration(migrations.Migration):
    dependencies = [
        ("elections", "0007_anonymize_ballot_storage"),
        ("auditlog", "0017_add_actor_email"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(scrub_ballot_audit_entries, migrations.RunPython.noop),
    ]
