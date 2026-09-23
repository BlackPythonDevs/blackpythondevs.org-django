"""The Executorship Election: the public page + council-only candidacy statements.

Access to `elections:statement` is gated on membership of the "Leadership
Council" group, same as `nominations` — not on model permissions, since that
group deliberately carries none (see test_groups.py). A signed-in member who
isn't on the council gets a 403, not a login redirect.
"""

import datetime
import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import COUNCIL_GROUP_NAME, Leader
from elections.forms import ElectionAdminForm
from elections.models import Candidacy, Election, closes_instant, default_election_year, opens_instant

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


class TestIntroMarkdown:
    def test_renders_markdown_to_html(self):
        election = make_election(intro="Nominate your **favorite** council member.")
        assert "<strong>favorite</strong>" in election.intro_html

    def test_strips_html_the_admin_pasted_in(self):
        election = make_election(intro='Hello <script>alert("hi")</script> world.')
        # The tag itself is stripped so nothing executes; bleach leaves its
        # inner text behind as plain text, same as any other disallowed tag.
        assert "<script>" not in election.intro_html
        assert "</script>" not in election.intro_html

    def test_blank_intro_is_blank_html(self):
        assert make_election(intro="").intro_html == ""


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

    def test_candidate_card_shows_region_affiliations_and_social_links(self, client, council_member):
        # Set directly, not via `country`: User.save() re-derives `region`
        # from `country` whenever one's set, which would overwrite this.
        council_member.region = "North America"
        council_member.twitter = "https://x.com/example"
        council_member.mastodon = "https://mastodon.social/@example"
        council_member.linkedin = "https://www.linkedin.com/in/example"
        council_member.save()
        Leader.objects.create(name=str(council_member), user=council_member, affiliations="PyLadies ATL")

        election = make_election()
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        html = client.get("/elections/").content.decode()

        assert "North America" in html
        assert "PyLadies ATL" in html
        assert "https://x.com/example" in html
        assert "https://mastodon.social/@example" in html
        assert "https://www.linkedin.com/in/example" in html

    def test_cta_reads_write_when_the_viewer_has_no_statement_yet(self, client, council_member):
        make_election(phase="nominating")
        client.force_login(council_member)
        html = client.get("/elections/").content.decode()
        assert "Write your candidacy statement" in html
        assert "Update your candidacy statement" not in html
        assert "Remove your statement" not in html

    def test_cta_reads_update_and_offers_removal_once_the_viewer_has_one(self, client, council_member):
        election = make_election(phase="nominating")
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        client.force_login(council_member)
        html = client.get("/elections/").content.decode()
        assert "Update your candidacy statement" in html
        assert "Remove your statement" in html
        assert "Write your candidacy statement" not in html

    def test_someone_elses_statement_does_not_change_your_cta(self, client, council_member, plain_member):
        election = make_election(phase="nominating")
        other = make_user("other_council", COUNCIL_GROUP_NAME, display_name="Other Council")
        Candidacy.objects.create(election=election, user=other, statement="Vote for them.")
        client.force_login(council_member)
        html = client.get("/elections/").content.decode()
        assert "Write your candidacy statement" in html


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


class TestCandidacyRemoval:
    def test_anonymous_is_redirected_to_login(self, client):
        make_election()
        response = client.get("/elections/statement/remove/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_member_outside_council_is_forbidden(self, client, plain_member):
        make_election()
        client.force_login(plain_member)
        assert client.get("/elections/statement/remove/").status_code == 403

    def test_get_shows_a_confirmation_without_deleting(self, client, council_member):
        election = make_election(phase="nominating")
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        client.force_login(council_member)
        response = client.get("/elections/statement/remove/")
        assert response.status_code == 200
        assert "Remove your candidacy statement" in response.content.decode()
        assert Candidacy.objects.count() == 1

    def test_post_deletes_the_statement(self, client, council_member):
        election = make_election(phase="nominating")
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        client.force_login(council_member)
        response = client.post("/elections/statement/remove/")
        assert response.status_code == 302
        assert response["Location"] == "/elections/"
        assert Candidacy.objects.count() == 0

    def test_without_a_statement_is_a_404(self, client, council_member):
        make_election(phase="nominating")
        client.force_login(council_member)
        assert client.get("/elections/statement/remove/").status_code == 404

    def test_cannot_remove_someone_elses_statement(self, client, council_member):
        election = make_election(phase="nominating")
        other = make_user("other_council", COUNCIL_GROUP_NAME, display_name="Other Council")
        Candidacy.objects.create(election=election, user=other, statement="Vote for them.")
        client.force_login(council_member)
        # There's no per-candidacy URL to target — this always resolves to
        # *your own* record, so a missing one of yours is just a 404, not a
        # way to delete someone else's.
        assert client.get("/elections/statement/remove/").status_code == 404
        assert Candidacy.objects.count() == 1

    def test_blocked_once_nominations_close(self, client, council_member):
        election = make_election(phase="voting")
        Candidacy.objects.create(election=election, user=council_member, statement="Vote for me.")
        client.force_login(council_member)
        response = client.post("/elections/statement/remove/", follow=True)
        assert "open right now" in response.content.decode()
        assert Candidacy.objects.count() == 1


class TestMemberAreaElectionsPanel:
    def test_council_member_sees_write_statement_while_nominating(self, client, council_member):
        make_election(phase="nominating")
        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert "Executorship Election" in html
        assert "Write your statement" in html

    def test_council_member_sees_view_only_outside_the_nomination_window(self, client, council_member):
        make_election(phase="voting")
        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert "Executorship Election" in html
        assert "Write your statement" not in html
        assert "See the election page" in html

    def test_no_election_yet_still_shows_the_panel_without_a_write_cta(self, client, council_member):
        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert "Executorship Election" in html
        assert "Write your statement" not in html

    def test_plain_member_does_not_see_the_election_panel(self, client, plain_member):
        make_election(phase="nominating")
        client.force_login(plain_member)
        assert "Executorship Election" not in client.get("/members/").content.decode()


class TestElectionYearAndTable:
    def test_default_year_is_next_calendar_year(self):
        assert default_election_year() == timezone.now().year + 1

    def test_table_name_is_specific(self):
        assert Election._meta.db_table == "executor_elections"


class TestOpensAndClosesInstant:
    def test_opens_at_the_earliest_instant_the_date_exists_anywhere(self):
        # UTC+14 (the first timezone to reach a new date) hits midnight 14
        # hours before UTC does.
        when = opens_instant(datetime.date(2027, 3, 10))
        assert when.isoformat() == "2027-03-09T10:00:00+00:00"

    def test_closes_at_the_latest_instant_the_date_is_still_going_anywhere(self):
        # AOE (UTC-12, the last timezone still on that date) doesn't roll
        # over to the next date until 12 hours after UTC does.
        when = closes_instant(datetime.date(2027, 3, 10))
        assert when.isoformat() == "2027-03-11T12:00:00+00:00"


class TestCreateElectionCommand:
    def test_creates_then_updates_the_same_year(self):
        call_command(
            "create_election",
            "2030",
            "--nomination-opens",
            "2030-01-01",
            "--nomination-closes",
            "2030-01-15",
            "--voting-opens",
            "2030-01-20",
            "--voting-closes",
            "2030-02-03",
        )
        assert Election.objects.count() == 1
        election = Election.objects.get(year=2030)
        assert election.nomination_closes_at == closes_instant(datetime.date(2030, 1, 15))

        call_command(
            "create_election",
            "2030",
            "--nomination-opens",
            "2030-01-01",
            "--nomination-closes",
            "2030-01-20",
            "--voting-opens",
            "2030-01-25",
            "--voting-closes",
            "2030-02-08",
        )
        assert Election.objects.count() == 1
        election.refresh_from_db()
        assert election.nomination_closes_at == closes_instant(datetime.date(2030, 1, 20))

    def test_defaults_to_next_calendar_year_when_year_is_omitted(self):
        call_command(
            "create_election",
            "--nomination-opens",
            "2030-01-01",
            "--nomination-closes",
            "2030-01-15",
            "--voting-opens",
            "2030-01-20",
            "--voting-closes",
            "2030-02-03",
        )
        assert Election.objects.get().year == default_election_year()

    def test_rejects_out_of_order_windows(self):
        with pytest.raises(CommandError):
            call_command(
                "create_election",
                "2031",
                "--nomination-opens",
                "2031-01-15",
                "--nomination-closes",
                "2031-01-01",
                "--voting-opens",
                "2031-02-01",
                "--voting-closes",
                "2031-02-15",
            )
        assert Election.objects.count() == 0

    def test_warns_but_allows_overlapping_windows(self):
        # Opens use the earliest timezone and closes use the latest, so this
        # is an expected consequence of the design, not an error to reject.
        out = io.StringIO()
        call_command(
            "create_election",
            "2032",
            "--nomination-opens",
            "2032-01-01",
            "--nomination-closes",
            "2032-01-20",
            "--voting-opens",
            "2032-01-10",
            "--voting-closes",
            "2032-02-01",
            stdout=out,
        )
        assert Election.objects.count() == 1
        assert "overlap" in out.getvalue()


VALID_ADMIN_FORM_DATA = {
    "year": "2033",
    "intro": "",
    "nomination_opens": "2033-01-01",
    "nomination_closes": "2033-01-15",
    "voting_opens": "2033-01-20",
    "voting_closes": "2033-02-03",
}


class TestElectionAdminForm:
    def test_valid_dates_produce_the_same_instants_as_the_command(self):
        form = ElectionAdminForm(data=VALID_ADMIN_FORM_DATA)
        assert form.is_valid(), form.errors
        election = form.save()
        assert election.nomination_opens_at == opens_instant(datetime.date(2033, 1, 1))
        assert election.nomination_closes_at == closes_instant(datetime.date(2033, 1, 15))
        assert election.voting_opens_at == opens_instant(datetime.date(2033, 1, 20))
        assert election.voting_closes_at == closes_instant(datetime.date(2033, 2, 3))

    def test_overlapping_windows_are_allowed_not_an_error(self):
        # Opens use the earliest timezone and closes use the latest, so
        # adjacent/overlapping dates are an expected trade-off, not a mistake
        # the form should block.
        data = VALID_ADMIN_FORM_DATA | {"voting_opens": "2033-01-05"}
        form = ElectionAdminForm(data=data)
        assert form.is_valid(), form.errors
        election = form.save()
        assert election.voting_opens_at < election.nomination_closes_at

    def test_editing_an_existing_election_prefills_the_original_dates(self):
        # Built directly from opens_instant/closes_instant (not
        # make_election's now-relative windows, which aren't aligned to
        # either) so pre-filling and resubmitting is expected to reproduce
        # these exact instants.
        election = Election.objects.create(
            year=2034,
            nomination_opens_at=opens_instant(datetime.date(2034, 1, 1)),
            nomination_closes_at=closes_instant(datetime.date(2034, 1, 15)),
            voting_opens_at=opens_instant(datetime.date(2034, 1, 20)),
            voting_closes_at=closes_instant(datetime.date(2034, 2, 3)),
        )
        form = ElectionAdminForm(instance=election)
        assert form.fields["nomination_opens"].initial == datetime.date(2034, 1, 1)
        assert form.fields["nomination_closes"].initial == datetime.date(2034, 1, 15)
        assert form.fields["voting_opens"].initial == datetime.date(2034, 1, 20)
        assert form.fields["voting_closes"].initial == datetime.date(2034, 2, 3)

        recomputed = ElectionAdminForm(
            data={
                "year": election.year,
                "intro": election.intro,
                "nomination_opens": form.fields["nomination_opens"].initial,
                "nomination_closes": form.fields["nomination_closes"].initial,
                "voting_opens": form.fields["voting_opens"].initial,
                "voting_closes": form.fields["voting_closes"].initial,
            },
            instance=election,
        )
        assert recomputed.is_valid(), recomputed.errors
        saved = recomputed.save()
        assert saved.nomination_opens_at == election.nomination_opens_at
        assert saved.nomination_closes_at == election.nomination_closes_at
        assert saved.voting_opens_at == election.voting_opens_at
        assert saved.voting_closes_at == election.voting_closes_at
