"""Community Service Award nominations: who can nominate, and what a
nominator can do after.

Access is gated on the Leadership Council / Executor groups (see
`core.models.is_leadership_or_above`) — not on model permissions, because
those groups deliberately carry none. A signed-in member who isn't in
leadership gets a 403, not a login redirect.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from core.models import COUNCIL_GROUP_NAME, EXECUTOR_GROUP_NAME
from service_award.models import ServiceAwardNomination, ServiceAwardRecipient, current_award_year

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leadership_groups(db):
    # The data migration creates these in the real DB; ensure they exist for
    # the in-memory test DB too.
    Group.objects.get_or_create(name=COUNCIL_GROUP_NAME)
    Group.objects.get_or_create(name=EXECUTOR_GROUP_NAME)


def make_user(username, group=None, **kwargs):
    # Already onboarded: these fixtures exercise leadership access, not the
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
def executor(db):
    return make_user("executor", EXECUTOR_GROUP_NAME, display_name="Ex Ecutor")


@pytest.fixture
def plain_member(db):
    return make_user("member")


def make_nomination(nominator, **kwargs):
    defaults = {
        "nominee_name": "Nia Nominee",
        "nominee_email": "nia@example.com",
        "statement": "She's been running the mentorship circle for two years.",
        "award_year": current_award_year(),
    }
    defaults.update(kwargs)
    return ServiceAwardNomination.objects.create(nominator=nominator, **defaults)


FORM_DATA = {
    "nominee_name": "Nia Nominee",
    "nominee_email": "nia@example.com",
    "nominee_url": "https://github.com/nia",
    "statement": "She's been running the mentorship circle for two years.",
    "contributions": "Mentorship circle, two PyCon talks.",
}


class TestAccess:
    @pytest.mark.parametrize("path", ["/leadership/service-award/", "/leadership/service-award/new/"])
    def test_anonymous_is_redirected_to_login(self, client, path):
        response = client.get(path)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    @pytest.mark.parametrize("path", ["/leadership/service-award/", "/leadership/service-award/new/"])
    def test_member_outside_leadership_is_forbidden(self, client, plain_member, path):
        client.force_login(plain_member)
        # 403, not a login redirect: they're signed in, they just aren't leadership.
        assert client.get(path).status_code == 403

    @pytest.mark.parametrize("fixture", ["council_member", "executor"])
    def test_council_and_executors_get_in(self, client, request, fixture):
        client.force_login(request.getfixturevalue(fixture))
        assert client.get("/leadership/service-award/").status_code == 200

    def test_superuser_gets_in(self, client, db):
        admin = get_user_model().objects.create_superuser(username="root", email="root@example.com", password="pw")
        client.force_login(admin)
        assert client.get("/leadership/service-award/").status_code == 200


class TestNominate:
    def test_leader_can_submit_a_nomination(self, client, executor):
        client.force_login(executor)
        response = client.post("/leadership/service-award/new/", FORM_DATA)
        assert response.status_code == 302
        assert response["Location"] == "/leadership/service-award/"

        nomination = ServiceAwardNomination.objects.get()
        assert nomination.nominator == executor
        assert nomination.nominee_name == "Nia Nominee"
        assert nomination.status == ServiceAwardNomination.SUBMITTED
        assert nomination.award_year == current_award_year()

    def test_duplicate_nomination_is_a_form_error_not_a_crash(self, client, executor):
        make_nomination(executor)
        client.force_login(executor)
        response = client.post("/leadership/service-award/new/", FORM_DATA)
        assert response.status_code == 200
        assert "already nominated this person" in response.content.decode()
        assert ServiceAwardNomination.objects.count() == 1

    def test_two_leaders_may_nominate_the_same_person(self, client, executor, council_member):
        make_nomination(executor)
        client.force_login(council_member)
        response = client.post("/leadership/service-award/new/", FORM_DATA)
        assert response.status_code == 302
        assert ServiceAwardNomination.objects.filter(nominee_email="nia@example.com").count() == 2

    def test_leadership_member_is_not_eligible(self, client, executor, council_member):
        client.force_login(executor)
        response = client.post(
            "/leadership/service-award/new/",
            FORM_DATA | {"nominee_user": council_member.pk},
        )
        assert response.status_code == 200
        assert "eligible for this award" in response.content.decode()
        assert ServiceAwardNomination.objects.count() == 0

    def test_previous_recipient_is_not_eligible(self, client, executor):
        ServiceAwardRecipient.objects.create(
            recipient_name="Nia Nominee", recipient_email="nia@example.com", award_year=current_award_year() - 1
        )
        client.force_login(executor)
        response = client.post("/leadership/service-award/new/", FORM_DATA)
        assert response.status_code == 200
        assert "already received the Community Service Award" in response.content.decode()
        assert ServiceAwardNomination.objects.count() == 0


class TestListView:
    def test_list_shows_only_the_selected_cycle(self, client, executor):
        make_nomination(executor, nominee_name="This Year")
        make_nomination(
            executor,
            nominee_name="Last Year",
            nominee_email="last@example.com",
            award_year=current_award_year() - 1,
        )
        client.force_login(executor)

        html = client.get("/leadership/service-award/").content.decode()
        assert "This Year" in html
        assert "Last Year" not in html

        html = client.get(f"/leadership/service-award/?year={current_award_year() - 1}").content.decode()
        assert "Last Year" in html

    def test_bad_year_falls_back_to_the_current_cycle(self, client, executor):
        make_nomination(executor, nominee_name="This Year")
        client.force_login(executor)
        html = client.get("/leadership/service-award/?year=nonsense").content.decode()
        assert "This Year" in html


class TestEditAndWithdraw:
    def test_nominator_can_edit_their_own_open_nomination(self, client, executor):
        nomination = make_nomination(executor)
        client.force_login(executor)
        response = client.post(
            f"/leadership/service-award/{nomination.pk}/edit/",
            FORM_DATA | {"statement": "Updated reasoning."},
        )
        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.statement == "Updated reasoning."

    def test_another_leader_cannot_edit_someone_elses_nomination(self, client, executor, council_member):
        nomination = make_nomination(executor)
        client.force_login(council_member)
        assert client.get(f"/leadership/service-award/{nomination.pk}/edit/").status_code == 403

    def test_decided_nomination_can_no_longer_be_edited(self, client, executor):
        nomination = make_nomination(executor, status=ServiceAwardNomination.ACCEPTED)
        client.force_login(executor)
        assert client.get(f"/leadership/service-award/{nomination.pk}/edit/").status_code == 403

    def test_nominator_can_withdraw_and_the_record_survives(self, client, executor):
        nomination = make_nomination(executor)
        client.force_login(executor)
        response = client.post(f"/leadership/service-award/{nomination.pk}/withdraw/")
        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.status == ServiceAwardNomination.WITHDRAWN

    def test_withdraw_rejects_someone_elses_nomination(self, client, executor, council_member):
        nomination = make_nomination(executor)
        client.force_login(council_member)
        assert client.post(f"/leadership/service-award/{nomination.pk}/withdraw/").status_code == 403
        nomination.refresh_from_db()
        assert nomination.status == ServiceAwardNomination.SUBMITTED


class TestDetailView:
    def test_edit_controls_only_show_for_the_nominator(self, client, executor, council_member):
        nomination = make_nomination(executor)

        client.force_login(executor)
        assert (
            "Withdraw this nomination"
            in client.get(f"/leadership/service-award/{nomination.pk}/").content.decode()
        )

        client.force_login(council_member)
        assert (
            "Withdraw this nomination"
            not in client.get(f"/leadership/service-award/{nomination.pk}/").content.decode()
        )


class TestMemberArea:
    def test_leaders_see_the_service_award_panel(self, client, executor):
        client.force_login(executor)
        assert "Community Service Award" in client.get("/members/").content.decode()

    def test_other_members_do_not(self, client, plain_member):
        client.force_login(plain_member)
        assert "Community Service Award" not in client.get("/members/").content.decode()
