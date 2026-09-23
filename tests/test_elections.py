"""Council elections: the public page + council-only candidacy statements.

Access to `elections:statement` is gated on membership of the "Leadership
Council" group, same as `nominations` — not on model permissions, since that
group deliberately carries none (see test_groups.py). A signed-in member who
isn't on the council gets a 403, not a login redirect.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import COUNCIL_GROUP_NAME
from elections.models import Candidacy, Election

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def council_group(db):
    # The data migration creates this in the real DB; ensure it exists for
    # the in-memory test DB too.
    Group.objects.get_or_create(name=COUNCIL_GROUP_NAME)


def make_user(username, group=None, **kwargs):
    # Already onboarded: these fixtures exercise election access, not the
    # onboarding survey that would otherwise redirect a fresh account.
    kwargs.setdefault("onboarding_completed_at", timezone.now())
    user = get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="pw", **kwargs
    )
    if group:
        user.groups.add(Group.objects.get(name=group))
    return user


@pytest.fixture
def council_member(db):
    return make_user("councilor", COUNCIL_GROUP_NAME, display_name="Cee Member")


@pytest.fixture
def plain_member(db):
    return make_user("member")


def make_election(year=None, phase="nominating", **overrides):
    """An election whose four dates put it squarely in `phase`."""
    now = timezone.now()
    year = year or now.year
    windows = {
        "upcoming": {
            "nomination_opens_at": now + datetime.timedelta(days=1),
            "nomination_closes_at": now + datetime.timedelta(days=8),
            "voting_opens_at": now + datetime.timedelta(days=9),
            "voting_closes_at": now + datetime.timedelta(days=16),
        },
        "nominating": {
            "nomination_opens_at": now - datetime.timedelta(days=1),
            "nomination_closes_at": now + datetime.timedelta(days=6),
            "voting_opens_at": now + datetime.timedelta(days=7),
            "voting_closes_at": now + datetime.timedelta(days=14),
        },
        "between": {
            "nomination_opens_at": now - datetime.timedelta(days=8),
            "nomination_closes_at": now - datetime.timedelta(days=1),
            "voting_opens_at": now + datetime.timedelta(days=6),
            "voting_closes_at": now + datetime.timedelta(days=13),
        },
        "voting": {
            "nomination_opens_at": now - datetime.timedelta(days=14),
            "nomination_closes_at": now - datetime.timedelta(days=7),
            "voting_opens_at": now - datetime.timedelta(days=1),
            "voting_closes_at": now + datetime.timedelta(days=6),
        },
        "closed": {
            "nomination_opens_at": now - datetime.timedelta(days=21),
            "nomination_closes_at": now - datetime.timedelta(days=14),
            "voting_opens_at": now - datetime.timedelta(days=7),
            "voting_closes_at": now - datetime.timedelta(days=1),
        },
    }[phase]
    windows.update(overrides)
    return Election.objects.create(year=year, **windows)


class TestElectionPhase:
    @pytest.mark.parametrize("phase", ["upcoming", "nominating", "between", "voting", "closed"])
    def test_phase_matches_its_windows(self, phase):
        assert make_election(phase=phase).phase == phase

    def test_next_deadline_tracks_the_current_phase(self):
        election = make_election(phase="nominating")
        label, when = election.next_deadline
        assert label == "Nominations close"
        assert when == election.nomination_closes_at

    def test_no_next_deadline_once_closed(self):
        assert make_election(phase="closed").next_deadline is None


class TestElectionDetailView:
    def test_public_page_lists_candidates(self, client, council_member):
        election = make_election()
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        html = client.get("/elections/").content.decode()
        assert "Vote for me." in html
        assert str(council_member) in html

    def test_no_election_scheduled_is_not_an_error(self, client):
        response = client.get("/elections/")
        assert response.status_code == 200
        assert "no election scheduled" in response.content.decode()

    def test_year_param_switches_cycles(self, client, council_member):
        this_year = make_election(year=timezone.now().year, phase="nominating")
        last_year = make_election(year=this_year.year - 1, phase="closed")
        Candidacy.objects.create(election=this_year, user=council_member, statement="This years pitch.")
        Candidacy.objects.create(election=last_year, user=council_member, statement="Last years pitch.")

        html = client.get("/elections/").content.decode()
        assert "This years pitch." in html
        assert "Last years pitch." not in html

        html = client.get(f"/elections/?year={last_year.year}").content.decode()
        assert "Last years pitch." in html

    def test_bad_year_falls_back_to_the_latest_election(self, client, council_member):
        election = make_election()
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        html = client.get("/elections/?year=nonsense").content.decode()
        assert "Vote for me." in html


class TestCandidacyStatement:
    def test_anonymous_is_redirected_to_login(self, client):
        make_election()
        response = client.get("/elections/statement/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_member_outside_council_is_forbidden(self, client, plain_member):
        make_election()
        client.force_login(plain_member)
        assert client.get("/elections/statement/").status_code == 403

    def test_council_member_can_submit_a_statement(self, client, council_member):
        election = make_election()
        client.force_login(council_member)
        response = client.post("/elections/statement/", {"statement": "I'd love to serve another term."})
        assert response.status_code == 302
        assert response["Location"] == "/elections/"

        candidacy = Candidacy.objects.get(election=election, user=council_member)
        assert candidacy.statement == "I'd love to serve another term."

    def test_council_member_can_update_their_own_statement(self, client, council_member):
        election = make_election()
        candidacy = Candidacy.objects.create(election=election, user=council_member, statement="Draft.")
        client.force_login(council_member)
        client.post("/elections/statement/", {"statement": "Final version."})
        candidacy.refresh_from_db()
        assert candidacy.statement == "Final version."

    def test_blocked_once_nominations_close(self, client, council_member):
        make_election(phase="voting")
        client.force_login(council_member)
        response = client.get("/elections/statement/", follow=True)
        assert "open right now" in response.content.decode()
        assert Candidacy.objects.count() == 0

    def test_superuser_gets_in(self, client, db):
        make_election()
        admin = get_user_model().objects.create_superuser(username="root", email="root@example.com", password="pw")
        client.force_login(admin)
        assert client.get("/elections/statement/").status_code == 200


class TestCreateElectionCommand:
    def test_creates_then_updates_the_same_year(self):
        call_command(
            "create_election",
            "2030",
            "--nomination-opens",
            "2030-01-01T00:00",
            "--nomination-closes",
            "2030-01-15T00:00",
            "--voting-opens",
            "2030-01-16T00:00",
            "--voting-closes",
            "2030-01-30T00:00",
        )
        assert Election.objects.count() == 1
        election = Election.objects.get(year=2030)
        assert election.nomination_closes_at.day == 15

        call_command(
            "create_election",
            "2030",
            "--nomination-opens",
            "2030-01-01T00:00",
            "--nomination-closes",
            "2030-01-20T00:00",
            "--voting-opens",
            "2030-01-21T00:00",
            "--voting-closes",
            "2030-02-04T00:00",
        )
        assert Election.objects.count() == 1
        election.refresh_from_db()
        assert election.nomination_closes_at.day == 20

    def test_rejects_out_of_order_windows(self):
        with pytest.raises(CommandError):
            call_command(
                "create_election",
                "2031",
                "--nomination-opens",
                "2031-01-15T00:00",
                "--nomination-closes",
                "2031-01-01T00:00",
                "--voting-opens",
                "2031-02-01T00:00",
                "--voting-closes",
                "2031-02-15T00:00",
            )
        assert Election.objects.count() == 0
