"""Council nominations: who can nominate, and what a nominator can do after.

Access is gated on membership of the "Leadership Council" / "Leadership" groups
— not on model permissions, because those groups deliberately carry none (see
test_groups.py). A signed-in member who isn't in leadership gets a 403, not a
login redirect.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from core.models import COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME
from nominations.models import CouncilNomination, current_term_year

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leadership_groups(db):
    # The data migration creates these in the real DB; ensure they exist for
    # the in-memory test DB too.
    for name in (COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME):
        Group.objects.get_or_create(name=name)


def make_user(username, group=None, **kwargs):
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
def leader(db):
    return make_user("leader", LEADERSHIP_GROUP_NAME, display_name="Lee Ader")


@pytest.fixture
def plain_member(db):
    return make_user("member")


def make_nomination(nominator, **kwargs):
    defaults = {
        "nominee_name": "Nia Nominee",
        "nominee_email": "nia@example.com",
        "statement": "She's been running the mentorship circle for two years.",
        "term_year": current_term_year(),
    }
    defaults.update(kwargs)
    return CouncilNomination.objects.create(nominator=nominator, **defaults)


FORM_DATA = {
    "nominee_name": "Nia Nominee",
    "nominee_email": "nia@example.com",
    "nominee_url": "https://github.com/nia",
    "statement": "She's been running the mentorship circle for two years.",
    "contributions": "Mentorship circle, two PyCon talks.",
    "nominee_consulted": "on",
}


class TestAccess:
    @pytest.mark.parametrize("path", ["/council/nominations/", "/council/nominations/new/"])
    def test_anonymous_is_redirected_to_login(self, client, path):
        response = client.get(path)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    @pytest.mark.parametrize("path", ["/council/nominations/", "/council/nominations/new/"])
    def test_member_outside_leadership_is_forbidden(self, client, plain_member, path):
        client.force_login(plain_member)
        # 403, not a login redirect: they're signed in, they just aren't leadership.
        assert client.get(path).status_code == 403

    @pytest.mark.parametrize("fixture", ["council_member", "leader"])
    def test_council_and_leaders_get_in(self, client, request, fixture):
        client.force_login(request.getfixturevalue(fixture))
        assert client.get("/council/nominations/").status_code == 200

    def test_superuser_gets_in(self, client, db):
        admin = get_user_model().objects.create_superuser(username="root", email="root@example.com", password="pw")
        client.force_login(admin)
        assert client.get("/council/nominations/").status_code == 200


class TestNominate:
    def test_leader_can_submit_a_nomination(self, client, leader):
        client.force_login(leader)
        response = client.post("/council/nominations/new/", FORM_DATA)
        assert response.status_code == 302
        assert response["Location"] == "/council/nominations/"

        nomination = CouncilNomination.objects.get()
        assert nomination.nominator == leader
        assert nomination.nominee_name == "Nia Nominee"
        assert nomination.status == CouncilNomination.SUBMITTED
        assert nomination.term_year == current_term_year()
        assert nomination.nominee_consulted is True

    def test_duplicate_nomination_is_a_form_error_not_a_crash(self, client, leader):
        make_nomination(leader)
        client.force_login(leader)
        response = client.post("/council/nominations/new/", FORM_DATA)
        assert response.status_code == 200
        assert "already nominated this person" in response.content.decode()
        assert CouncilNomination.objects.count() == 1

    def test_two_leaders_may_nominate_the_same_person(self, client, leader, council_member):
        make_nomination(leader)
        client.force_login(council_member)
        response = client.post("/council/nominations/new/", FORM_DATA)
        assert response.status_code == 302
        assert CouncilNomination.objects.filter(nominee_email="nia@example.com").count() == 2


class TestListView:
    def test_list_shows_only_the_selected_cycle(self, client, leader):
        make_nomination(leader, nominee_name="This Year")
        make_nomination(
            leader,
            nominee_name="Last Year",
            nominee_email="last@example.com",
            term_year=current_term_year() - 1,
        )
        client.force_login(leader)

        html = client.get("/council/nominations/").content.decode()
        assert "This Year" in html
        assert "Last Year" not in html

        html = client.get(f"/council/nominations/?year={current_term_year() - 1}").content.decode()
        assert "Last Year" in html

    def test_bad_year_falls_back_to_the_current_cycle(self, client, leader):
        make_nomination(leader, nominee_name="This Year")
        client.force_login(leader)
        html = client.get("/council/nominations/?year=nonsense").content.decode()
        assert "This Year" in html


class TestEditAndWithdraw:
    def test_nominator_can_edit_their_own_open_nomination(self, client, leader):
        nomination = make_nomination(leader)
        client.force_login(leader)
        response = client.post(
            f"/council/nominations/{nomination.pk}/edit/",
            FORM_DATA | {"statement": "Updated reasoning."},
        )
        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.statement == "Updated reasoning."

    def test_another_leader_cannot_edit_someone_elses_nomination(self, client, leader, council_member):
        nomination = make_nomination(leader)
        client.force_login(council_member)
        assert client.get(f"/council/nominations/{nomination.pk}/edit/").status_code == 403

    def test_decided_nomination_can_no_longer_be_edited(self, client, leader):
        nomination = make_nomination(leader, status=CouncilNomination.ACCEPTED)
        client.force_login(leader)
        assert client.get(f"/council/nominations/{nomination.pk}/edit/").status_code == 403

    def test_nominator_can_withdraw_and_the_record_survives(self, client, leader):
        nomination = make_nomination(leader)
        client.force_login(leader)
        response = client.post(f"/council/nominations/{nomination.pk}/withdraw/")
        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.WITHDRAWN

    def test_withdraw_rejects_someone_elses_nomination(self, client, leader, council_member):
        nomination = make_nomination(leader)
        client.force_login(council_member)
        assert client.post(f"/council/nominations/{nomination.pk}/withdraw/").status_code == 403
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.SUBMITTED


class TestDetailView:
    def test_edit_controls_only_show_for_the_nominator(self, client, leader, council_member):
        nomination = make_nomination(leader)

        client.force_login(leader)
        assert "Withdraw this nomination" in client.get(f"/council/nominations/{nomination.pk}/").content.decode()

        client.force_login(council_member)
        assert "Withdraw this nomination" not in client.get(f"/council/nominations/{nomination.pk}/").content.decode()


class TestMemberArea:
    def test_leaders_see_the_nominations_panel(self, client, leader):
        client.force_login(leader)
        assert "Nominate someone" in client.get("/members/").content.decode()

    def test_other_members_do_not(self, client, plain_member):
        client.force_login(plain_member)
        assert "Nominate someone" not in client.get("/members/").content.decode()
