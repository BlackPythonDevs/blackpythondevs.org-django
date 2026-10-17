"""Remove the two ways a stored ballot could be matched back to its voter's
`VoteRecord` without any join: `Ballot.submitted_at` (written in the same
request as `VoteRecord.voted_at`, milliseconds apart) and sequential primary
keys on `Ballot`/`BallotRanking` (the Nth ballot belonged to the Nth voter).

Both tables move to random UUID primary keys and `submitted_at` is dropped.
Existing ballots are kept: every ranking is re-pointed at its own ballot's new
id through an explicit old-id -> new-id map (`ballot_uuid`), and rows are
rewritten in shuffled order so their new ids don't preserve the old order.

Ballots from a concluded election live in these tables, so the migration
checks itself: `snapshot` fingerprints exactly what `tally_irv` reads (each
ballot's election and its sorted `(candidacy, rank)` pairs) plus ranking and
vote-record counts, and `verify` recomputes it at the end. Any difference
raises, and since Postgres runs the whole migration in one transaction,
nothing is committed. The same check runs in reverse.
"""

import random
import uuid
from collections import defaultdict

from django.db import migrations, models

# Filled by whichever of snapshot/verify runs first in this process and read
# by the other; both ends of the migration run in the same `migrate` call.
_SNAPSHOT = {}


def ballot_fingerprint(apps):
    """Everything the tally depends on, with ids stripped out: per election,
    the sorted list of ballots, each as its sorted `(candidacy_id, rank)`
    pairs. Primary keys change type across this migration, so they're only
    used to group rankings, never compared."""
    Ballot = apps.get_model("elections", "Ballot")
    BallotRanking = apps.get_model("elections", "BallotRanking")
    VoteRecord = apps.get_model("elections", "VoteRecord")

    ballots = {pk: (election_id, []) for pk, election_id in Ballot.objects.values_list("pk", "election_id")}
    for ballot_id, candidacy_id, rank in BallotRanking.objects.values_list("ballot_id", "candidacy_id", "rank"):
        if ballot_id not in ballots:
            raise RuntimeError("A ballot ranking is not attached to any ballot; refusing to continue.")
        ballots[ballot_id][1].append((candidacy_id, rank))

    by_election = defaultdict(list)
    for election_id, pairs in ballots.values():
        by_election[election_id].append(tuple(sorted(pairs)))

    vote_records = defaultdict(int)
    for election_id in VoteRecord.objects.values_list("election_id", flat=True):
        vote_records[election_id] += 1

    return {
        "ballots": {election_id: sorted(found) for election_id, found in by_election.items()},
        "ranking_count": BallotRanking.objects.count(),
        "vote_records": dict(vote_records),
    }


def snapshot(apps, schema_editor):
    _SNAPSHOT.clear()
    _SNAPSHOT.update(ballot_fingerprint(apps))


def verify(apps, schema_editor):
    if not _SNAPSHOT:
        raise RuntimeError("No ballot snapshot was taken at the start of this migration; refusing to commit.")
    expected = dict(_SNAPSHOT)
    _SNAPSHOT.clear()
    if ballot_fingerprint(apps) != expected:
        raise RuntimeError(
            "Ballot contents changed during migration; rolling back. No ballot data has been modified."
        )


def assign_uuids(apps, schema_editor):
    Ballot = apps.get_model("elections", "Ballot")
    BallotRanking = apps.get_model("elections", "BallotRanking")
    rng = random.SystemRandom()

    ballots = list(Ballot.objects.only("pk"))
    rng.shuffle(ballots)
    new_ids = {}
    for ballot in ballots:
        ballot.uuid = new_ids[ballot.pk] = uuid.uuid4()
        ballot.save(update_fields=["uuid"])

    rankings = list(BallotRanking.objects.only("pk", "ballot_id"))
    rng.shuffle(rankings)
    for ranking in rankings:
        ranking.uuid = uuid.uuid4()
        ranking.ballot_uuid = new_ids[ranking.ballot_id]
        ranking.save(update_fields=["uuid", "ballot_uuid"])


def unassign_uuids(apps, schema_editor):
    Ballot = apps.get_model("elections", "Ballot")
    BallotRanking = apps.get_model("elections", "BallotRanking")
    old_ids = dict(Ballot.objects.values_list("uuid", "pk"))
    for ranking in BallotRanking.objects.only("pk", "ballot_uuid"):
        ranking.ballot_id = old_ids[ranking.ballot_uuid]
        ranking.save(update_fields=["ballot"])


def link_rankings(apps, schema_editor):
    BallotRanking = apps.get_model("elections", "BallotRanking")
    rankings = list(BallotRanking.objects.only("pk", "ballot_uuid"))
    random.SystemRandom().shuffle(rankings)
    for ranking in rankings:
        ranking.ballot_id = ranking.ballot_uuid
        ranking.save(update_fields=["ballot"])


def unlink_rankings(apps, schema_editor):
    BallotRanking = apps.get_model("elections", "BallotRanking")
    for ranking in BallotRanking.objects.only("pk", "ballot_id"):
        ranking.ballot_uuid = ranking.ballot_id
        ranking.save(update_fields=["ballot_uuid"])


def _drop_primary_key_sql(table):
    return f"""
        DO $$ DECLARE pk text; BEGIN
            SELECT conname INTO pk FROM pg_constraint WHERE conrelid = '{table}'::regclass AND contype = 'p';
            EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', pk);
        END $$;
    """


class Migration(migrations.Migration):
    dependencies = [
        ("elections", "0006_remove_ballotranking_one_candidate_per_rank_per_ballot"),
    ]

    operations = [
        migrations.RunPython(snapshot, verify),
        migrations.RemoveConstraint(model_name="ballotranking", name="one_ranking_per_candidate_per_ballot"),
        migrations.AddField(model_name="ballot", name="uuid", field=models.UUIDField(null=True)),
        migrations.AddField(model_name="ballotranking", name="uuid", field=models.UUIDField(null=True)),
        migrations.AddField(model_name="ballotranking", name="ballot_uuid", field=models.UUIDField(null=True)),
        migrations.AlterField(
            model_name="ballotranking",
            name="ballot",
            field=models.ForeignKey(
                null=True, on_delete=models.deletion.CASCADE, related_name="rankings", to="elections.ballot"
            ),
        ),
        migrations.RunPython(assign_uuids, unassign_uuids),
        migrations.RemoveField(model_name="ballotranking", name="ballot"),
        migrations.RemoveField(model_name="ballot", name="id"),
        migrations.RemoveField(model_name="ballotranking", name="id"),
        migrations.AlterField(
            model_name="ballot",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="ballotranking",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
        ),
        # Reverse only: Django doesn't drop a primary key when a field stops
        # being one, so the AlterFields above can't be unapplied without this.
        migrations.RunSQL(migrations.RunSQL.noop, _drop_primary_key_sql("elections_ballotranking")),
        migrations.RunSQL(migrations.RunSQL.noop, _drop_primary_key_sql("elections_ballot")),
        migrations.RenameField(model_name="ballot", old_name="uuid", new_name="id"),
        migrations.RenameField(model_name="ballotranking", old_name="uuid", new_name="id"),
        migrations.AddField(
            model_name="ballotranking",
            name="ballot",
            field=models.ForeignKey(
                null=True, on_delete=models.deletion.CASCADE, related_name="rankings", to="elections.ballot"
            ),
        ),
        migrations.RunPython(link_rankings, unlink_rankings),
        migrations.RemoveField(model_name="ballotranking", name="ballot_uuid"),
        migrations.AlterField(
            model_name="ballotranking",
            name="ballot",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name="rankings", to="elections.ballot"
            ),
        ),
        migrations.RemoveField(model_name="ballot", name="submitted_at"),
        migrations.AddConstraint(
            model_name="ballotranking",
            constraint=models.UniqueConstraint(
                fields=("ballot", "candidacy"), name="one_ranking_per_candidate_per_ballot"
            ),
        ),
        migrations.RunPython(verify, snapshot),
    ]
