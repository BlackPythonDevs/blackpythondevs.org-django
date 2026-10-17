"""Ballots stay anonymous even to superusers: nothing an admin can see — the
audit trail, the admin changelists, or the ballot rows themselves — ties a
voter to their rankings. Who voted (`VoteRecord`) and the tally stay
available. See `elections.models.Ballot` and migration 0007.
"""

import datetime
import uuid

import pytest
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.models import COUNCIL_GROUP_NAME
from elections.models import Ballot, BallotRanking, Candidacy, Election, VoteRecord, regional_results
from tests.test_elections import council_group, make_election, make_user  # noqa: F401

BEFORE = [("elections", "0006_remove_ballotranking_one_candidate_per_rank_per_ballot")]
AFTER = [("elections", "0007_anonymize_ballot_storage")]


def make_superuser(username="root"):
    return get_user_model().objects.create_superuser(
        username=username, email=f"{username}@example.com", password="pw", onboarding_completed_at=timezone.now()
    )


def ballot_content_types():
    return ContentType.objects.get_for_models(Ballot, BallotRanking).values()


@pytest.mark.django_db
class TestAuditTrail:
    @pytest.fixture
    def election(self):
        election = make_election(phase="voting")
        self.first = Candidacy.objects.create(
            election=election, user=make_user("first", COUNCIL_GROUP_NAME, display_name="First"), statement="1"
        )
        self.second = Candidacy.objects.create(
            election=election, user=make_user("second", COUNCIL_GROUP_NAME, display_name="Second"), statement="2"
        )
        return election

    def vote(self, client, voter):
        client.force_login(voter)
        LogEntry.objects.all().delete()
        response = client.post("/elections/vote/", {f"rank_{self.first.pk}": "2", f"rank_{self.second.pk}": "1"})
        assert response.status_code == 302

    @pytest.mark.parametrize("voter_kind", ["council member", "superuser"])
    def test_casting_a_ballot_audits_only_who_voted(self, client, election, voter_kind):
        voter = make_superuser() if voter_kind == "superuser" else make_user("voter", COUNCIL_GROUP_NAME)
        self.vote(client, voter)

        assert not LogEntry.objects.filter(content_type__in=ballot_content_types()).exists()
        # The only entry naming the voter is the VoteRecord: that they voted, not how.
        voter_entries = LogEntry.objects.filter(actor=voter)
        assert [entry.content_type.model for entry in voter_entries] == ["voterecord"]
        ballot = Ballot.objects.get()
        for entry in LogEntry.objects.all():
            assert ballot.token not in str(entry.changes)
            assert str(ballot.pk) not in str(entry.changes)

    def test_deleting_a_ballot_audits_nothing(self, client, election):
        self.vote(client, make_user("voter", COUNCIL_GROUP_NAME))
        client.force_login(make_superuser())
        ballot = Ballot.objects.get()
        response = client.post(f"/django-admin/elections/ballot/{ballot.pk}/delete/", {"post": "yes"})
        assert response.status_code == 302
        assert not Ballot.objects.exists()
        assert not LogEntry.objects.filter(content_type__in=ballot_content_types()).exists()


@pytest.mark.django_db
class TestNoIndirectLink:
    def test_ballots_carry_no_timestamp_and_random_ids(self):
        ballot_fields = {field.name for field in Ballot._meta.get_fields()}
        assert not {"submitted_at", "user", "voted_at"} & ballot_fields
        assert Ballot._meta.pk.get_internal_type() == "UUIDField"
        assert BallotRanking._meta.pk.get_internal_type() == "UUIDField"

    def test_ballot_admin_shows_no_timestamps(self, client):
        election = make_election(phase="closed")
        candidacy = Candidacy.objects.create(election=election, user=make_user("cand"), statement="x")
        ballot = Ballot.objects.create(election=election)
        BallotRanking.objects.create(ballot=ballot, candidacy=candidacy, rank=1)
        client.force_login(make_superuser())

        for url in ("/django-admin/elections/ballot/", f"/django-admin/elections/ballot/{ballot.pk}/change/"):
            response = client.get(url)
            assert response.status_code == 200
            assert ballot.token in response.content.decode()
            assert "submitted" not in response.content.decode().lower()
        assert isinstance(ballot.pk, uuid.UUID)


@pytest.mark.django_db
class TestVotingStillWorks:
    def test_vote_once_reject_second_and_tally(self, client):
        election = make_election(phase="voting")
        alice = make_user("alice", COUNCIL_GROUP_NAME, display_name="Alice")
        bob = make_user("bob", COUNCIL_GROUP_NAME, display_name="Bob")
        a = Candidacy.objects.create(election=election, user=alice, statement="A")
        b = Candidacy.objects.create(election=election, user=bob, statement="B")

        client.force_login(alice)
        assert client.post("/elections/vote/", {f"rank_{a.pk}": "1", f"rank_{b.pk}": "2"}).status_code == 302
        second = client.post("/elections/vote/", {f"rank_{b.pk}": "1"}, follow=True)
        assert "already voted" in second.content.decode()

        client.force_login(bob)
        assert client.post("/elections/vote/", {f"rank_{a.pk}": "1"}).status_code == 302

        assert Ballot.objects.filter(election=election).count() == 2
        assert set(VoteRecord.objects.filter(election=election).values_list("user__username", flat=True)) == {
            "alice",
            "bob",
        }
        (rounds,) = regional_results(election).values()
        assert rounds[-1]["winner"] == a


@pytest.fixture
def migrate(transactional_db):
    """Run the elections app to `targets` and return that point's historical
    apps registry. Puts the schema back at the latest migration afterward."""

    def run(targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    yield run
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def seed_closed_election(apps):
    """A concluded two-region election at migration 0006, with integer ids.
    West A wins Western Africa only after an elimination round; Asia B wins
    South-eastern Asia outright."""
    # Only the elections app is rolled back, so users are already at their
    # latest schema — the real model, not 0006's historical one.
    User = get_user_model()
    Election = apps.get_model("elections", "Election")
    Candidacy = apps.get_model("elections", "Candidacy")
    Ballot = apps.get_model("elections", "Ballot")
    BallotRanking = apps.get_model("elections", "BallotRanking")
    VoteRecord = apps.get_model("elections", "VoteRecord")

    now = timezone.now()
    election = Election.objects.create(
        year=2026,
        nomination_opens_at=now - datetime.timedelta(days=30),
        nomination_closes_at=now - datetime.timedelta(days=20),
        voting_opens_at=now - datetime.timedelta(days=10),
        voting_closes_at=now - datetime.timedelta(days=1),
    )
    candidacies = {}
    for name, region in [
        ("West A", "Western Africa"),
        ("West B", "Western Africa"),
        ("West C", "Western Africa"),
        ("Asia A", "South-eastern Asia"),
        ("Asia B", "South-eastern Asia"),
    ]:
        user = User.objects.create(username=name, email=f"{name.replace(' ', '')}@example.com")
        User.objects.filter(pk=user.pk).update(region=region)  # region is derived on save(); set it directly
        candidacies[name] = Candidacy.objects.create(election=election, user_id=user.pk, statement=name)

    ballots = [
        ["West A", "Asia B"],
        ["West A", "Asia B"],
        ["West B", "West A", "Asia B"],
        ["West C", "Asia A"],
        ["West C", "West B", "Asia B"],
    ]
    for i, names in enumerate(ballots):
        voter = User.objects.create(username=f"voter{i}", email=f"voter{i}@example.com")
        ballot = Ballot.objects.create(election=election)
        for name in names:
            same_region = [n for n in names if n[:4] == name[:4]]
            BallotRanking.objects.create(ballot=ballot, candidacy=candidacies[name], rank=same_region.index(name) + 1)
        VoteRecord.objects.create(election=election, user_id=voter.pk)
    return {name: c.pk for name, c in candidacies.items()}


class TestMigration0007:
    def test_existing_ballots_keep_their_rankings_and_results(self, migrate):
        old_apps = migrate(BEFORE)
        candidacy_ids = seed_closed_election(old_apps)
        OldRanking = old_apps.get_model("elections", "BallotRanking")
        before = sorted(
            tuple(sorted(OldRanking.objects.filter(ballot_id=ballot_id).values_list("candidacy_id", "rank")))
            for ballot_id in OldRanking.objects.order_by().values_list("ballot_id", flat=True).distinct()
        )

        migrate(AFTER)

        election = Election.objects.get(year=2026)
        after = sorted(
            tuple(sorted(ballot.rankings.values_list("candidacy_id", "rank"))) for ballot in election.ballots.all()
        )
        assert after == before
        assert all(isinstance(pk, uuid.UUID) for pk in Ballot.objects.values_list("pk", flat=True))
        assert VoteRecord.objects.filter(election=election).count() == 5

        results = regional_results(election)
        assert results["Western Africa"][-1]["winner"].pk == candidacy_ids["West A"]
        assert len(results["Western Africa"]) > 1  # decided after an elimination
        assert results["South-eastern Asia"][-1]["winner"].pk == candidacy_ids["Asia B"]

    def test_a_mismatched_ballot_aborts_and_rolls_back(self, migrate):
        old_apps = migrate(BEFORE)
        seed_closed_election(old_apps)
        OldRanking = old_apps.get_model("elections", "BallotRanking")
        before = sorted(OldRanking.objects.values_list("id", "ballot_id", "candidacy_id", "rank"))

        executor = MigrationExecutor(connection)
        migration = executor.loader.get_migration(*AFTER[0])
        link_op = next(
            op for op in migration.operations if getattr(getattr(op, "code", None), "__name__", "") == "link_rankings"
        )
        real_link = link_op.code

        def misfile_one_ranking(apps, schema_editor):
            real_link(apps, schema_editor)
            Ballot = apps.get_model("elections", "Ballot")
            BallotRanking = apps.get_model("elections", "BallotRanking")
            ranking = BallotRanking.objects.first()
            # A ballot that doesn't rank this candidate yet, so it's the
            # fingerprint check that catches this, not the unique constraint.
            ranking.ballot = Ballot.objects.exclude(rankings__candidacy_id=ranking.candidacy_id).first()
            ranking.save()

        # Restored by hand rather than with monkeypatch: the `migrate` fixture's
        # teardown re-runs this migration and must see the real operation.
        link_op.code = misfile_one_ranking
        try:
            with pytest.raises(RuntimeError, match="Ballot contents changed"):
                executor.migrate(AFTER)
        finally:
            link_op.code = real_link

        # Still at 0006 with every ballot exactly as it was.
        assert MigrationExecutor(connection).loader.applied_migrations.keys() >= set(BEFORE)
        assert AFTER[0] not in MigrationExecutor(connection).loader.applied_migrations
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, ballot_id, candidacy_id, rank FROM elections_ballotranking ORDER BY id")
            assert sorted(cursor.fetchall()) == before


class TestMigration0008:
    SCRUB = [("elections", "0008_scrub_ballot_audit_entries")]

    def test_deletes_only_ballot_and_ranking_audit_entries(self, migrate):
        migrate(AFTER)
        election = make_election(phase="closed")
        voter = make_user("voter", COUNCIL_GROUP_NAME)
        candidacy = Candidacy.objects.create(election=election, user=make_user("cand"), statement="x")
        ballot = Ballot.objects.create(election=election)
        ranking = BallotRanking.objects.create(ballot=ballot, candidacy=candidacy, rank=1)
        vote = VoteRecord.objects.create(election=election, user=voter)

        def log(obj, actor):
            return LogEntry.objects.create(
                content_type=ContentType.objects.get_for_model(obj),
                object_pk=str(obj.pk),
                object_repr=str(obj),
                action=LogEntry.Action.CREATE,
                changes={"token": ["None", getattr(obj, "token", "")]},
                actor=actor,
            )

        log(ballot, voter)
        log(ranking, voter)
        log(vote, voter)
        log(candidacy, None)
        # Everything else (vote records, candidacies, the users and election
        # the fixtures just created) must survive.
        kept = set(LogEntry.objects.exclude(content_type__in=ballot_content_types()).values_list("pk", flat=True))
        assert {"voterecord", "candidacy"} <= set(
            LogEntry.objects.filter(pk__in=kept).values_list("content_type__model", flat=True)
        )

        migrate(self.SCRUB)

        assert set(LogEntry.objects.values_list("pk", flat=True)) == kept
        assert not LogEntry.objects.filter(content_type__in=ballot_content_types()).exists()
        # Ballots themselves are untouched.
        assert list(ballot.rankings.values_list("candidacy_id", "rank")) == [(candidacy.pk, 1)]
