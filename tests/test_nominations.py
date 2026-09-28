"""Council nominations: who can nominate, and what a nominator can do after.

Access is gated on membership of the "Leadership Council" group — not on
model permissions, because that group deliberately carries none (see
test_groups.py). A signed-in member who isn't in leadership gets a 403, not a
login redirect.
"""

import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from core.models import COUNCIL_GROUP_NAME, EXECUTOR_GROUP_NAME, ONBOARDING_GROUP_NAME, Leader
from nominations.models import CouncilNomination, current_term_year

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leadership_groups(db):
    # The data migrations create these in the real DB; ensure they exist for
    # the in-memory test DB too.
    Group.objects.get_or_create(name=COUNCIL_GROUP_NAME)
    Group.objects.get_or_create(name=EXECUTOR_GROUP_NAME)
    Group.objects.get_or_create(name=ONBOARDING_GROUP_NAME)


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
def leader(db):
    return make_user("leader", COUNCIL_GROUP_NAME, display_name="Lee Ader")


@pytest.fixture
def plain_member(db):
    return make_user("member")


@pytest.fixture
def executor(db):
    return make_user("executor", EXECUTOR_GROUP_NAME, display_name="Exe Cutor")


@pytest.fixture
def onboarding_member(db):
    return make_user("onboarder", ONBOARDING_GROUP_NAME, display_name="On Boarder")


def make_nomination(nominator, **kwargs):
    defaults = {
        "nominee_name": "Nia Nominee",
        "nominee_email": "nia@example.com",
        "statement": "She's been running the mentorship circle for two years.",
        "term_year": current_term_year(),
    }
    defaults.update(kwargs)
    return CouncilNomination.objects.create(nominator=nominator, **defaults)


def make_headshot():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format="JPEG")
    buffer.seek(0)
    return SimpleUploadedFile("headshot.jpg", buffer.read(), content_type="image/jpeg")


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
    def test_nominee_user_field_is_not_on_the_form(self, client, leader):
        client.force_login(leader)
        html = client.get("/council/nominations/new/").content.decode()
        assert "nominee_user" not in html
        assert "Their site account" not in html

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
    @pytest.mark.parametrize(
        "actor,status,allowed",
        [
            ("owner", CouncilNomination.SUBMITTED, True),
            ("other", CouncilNomination.SUBMITTED, False),
            ("owner", CouncilNomination.ACCEPTED, False),
        ],
        ids=["owner_can_edit_their_own_open_nomination", "another_leader_is_forbidden", "decided_is_forbidden"],
    )
    def test_edit_access(self, client, leader, council_member, actor, status, allowed):
        nomination = make_nomination(leader, status=status)
        client.force_login(leader if actor == "owner" else council_member)

        if allowed:
            response = client.post(
                f"/council/nominations/{nomination.pk}/edit/",
                FORM_DATA | {"statement": "Updated reasoning."},
            )
            assert response.status_code == 302
            nomination.refresh_from_db()
            assert nomination.statement == "Updated reasoning."
        else:
            assert client.get(f"/council/nominations/{nomination.pk}/edit/").status_code == 403

    @pytest.mark.parametrize(
        "actor,allowed",
        [("owner", True), ("other", False)],
        ids=["nominator_can_withdraw_and_the_record_survives", "withdraw_rejects_someone_elses_nomination"],
    )
    def test_withdraw_access(self, client, leader, council_member, actor, allowed):
        nomination = make_nomination(leader)
        client.force_login(leader if actor == "owner" else council_member)

        response = client.post(f"/council/nominations/{nomination.pk}/withdraw/")
        nomination.refresh_from_db()
        if allowed:
            assert response.status_code == 302
            assert nomination.status == CouncilNomination.WITHDRAWN
        else:
            assert response.status_code == 403
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


class TestSeconding:
    def test_nominator_cannot_second_their_own_nomination(self, client, leader):
        nomination = make_nomination(leader)
        client.force_login(leader)
        response = client.post(f"/council/nominations/{nomination.pk}/second/")
        assert response.status_code == 403
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.SUBMITTED

    def test_another_council_member_can_second(self, client, leader, council_member):
        nomination = make_nomination(leader)
        client.force_login(council_member)
        response = client.post(f"/council/nominations/{nomination.pk}/second/")
        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.SECONDED
        assert nomination.seconded_by == council_member
        assert nomination.objection_window_closes_at == nomination.seconded_at + timedelta(hours=24)

    def test_plain_member_cannot_second(self, client, leader, plain_member):
        nomination = make_nomination(leader)
        client.force_login(plain_member)
        assert client.post(f"/council/nominations/{nomination.pk}/second/").status_code == 403

    def test_already_seconded_nomination_cannot_be_seconded_again(self, client, leader, council_member, executor):
        nomination = make_nomination(leader)
        nomination.second(council_member)
        client.force_login(executor)
        response = client.post(f"/council/nominations/{nomination.pk}/second/")
        assert response.status_code == 403
        nomination.refresh_from_db()
        assert nomination.seconded_by == council_member


class TestObjections:
    def make_seconded_nomination(self, nominator, seconder, closes_at=None):
        nomination = make_nomination(nominator)
        nomination.second(seconder)
        if closes_at is not None:
            nomination.objection_window_closes_at = closes_at
            nomination.save(update_fields=["objection_window_closes_at"])
        return nomination

    def test_council_member_can_object_while_window_open(self, client, leader, council_member):
        nomination = self.make_seconded_nomination(leader, council_member)
        client.force_login(leader)
        response = client.post(f"/council/nominations/{nomination.pk}/object/", {"reason": "Not ready yet."})
        assert response.status_code == 302
        assert nomination.objections.count() == 1
        assert nomination.objections.get().submitted_by == leader

    def test_executor_can_object_too(self, client, leader, council_member, executor):
        nomination = self.make_seconded_nomination(leader, council_member)
        client.force_login(executor)
        response = client.post(f"/council/nominations/{nomination.pk}/object/", {"reason": "Concerned."})
        assert response.status_code == 302
        assert nomination.objections.count() == 1

    def test_plain_member_cannot_object(self, client, leader, council_member, plain_member):
        nomination = self.make_seconded_nomination(leader, council_member)
        client.force_login(plain_member)
        response = client.post(f"/council/nominations/{nomination.pk}/object/", {"reason": "..."})
        assert response.status_code == 403
        assert nomination.objections.count() == 0

    def test_objection_is_rejected_once_the_window_has_closed(self, client, leader, council_member):
        nomination = self.make_seconded_nomination(
            leader, council_member, closes_at=timezone.now() - timedelta(seconds=1)
        )
        client.force_login(leader)
        response = client.post(f"/council/nominations/{nomination.pk}/object/", {"reason": "Too late."})
        assert response.status_code == 403
        assert nomination.objections.count() == 0

    def test_objections_are_not_reachable_by_a_plain_member(self, client, leader, council_member, plain_member):
        nomination = self.make_seconded_nomination(leader, council_member)
        nomination.objections.create(submitted_by=leader, reason="Secret reason")
        client.force_login(plain_member)
        assert client.get(f"/council/nominations/{nomination.pk}/").status_code == 403


class TestSendConfirmation:
    def make_seconded_nomination(self, nominator, seconder, closes_at=None):
        nomination = make_nomination(nominator)
        nomination.second(seconder)
        if closes_at is not None:
            nomination.objection_window_closes_at = closes_at
            nomination.save(update_fields=["objection_window_closes_at"])
        return nomination

    def test_confirmation_is_refused_before_the_window_closes(self, client, leader, council_member):
        nomination = self.make_seconded_nomination(leader, council_member)
        client.force_login(leader)
        mail.outbox.clear()

        response = client.post(f"/council/nominations/{nomination.pk}/confirm/")

        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.SECONDED
        assert nomination.invite_link is None
        assert mail.outbox == []

    def test_confirmation_sends_one_email_and_creates_a_locked_invite(self, client, leader, council_member):
        nomination = self.make_seconded_nomination(
            leader, council_member, closes_at=timezone.now() - timedelta(seconds=1)
        )
        client.force_login(leader)
        mail.outbox.clear()

        response = client.post(f"/council/nominations/{nomination.pk}/confirm/")

        assert response.status_code == 302
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.CONFIRMATION_SENT
        assert nomination.invite_link is not None
        assert nomination.invite_link.email == nomination.nominee_email
        assert nomination.invite_link.max_uses == 1
        assert list(nomination.invite_link.groups.values_list("name", flat=True)) == [COUNCIL_GROUP_NAME]
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [nomination.nominee_email]


class TestAcceptanceAndOnboarding:
    """The full path from a sent confirmation to a drafted announcement."""

    def test_accepting_and_completing_the_profile_finishes_the_nomination(
        self, client, leader, council_member, onboarding_member, bootstrapped_site
    ):
        nomination = make_nomination(leader, nominee_email="newlead@example.com", nominee_name="New Lead")
        nomination.second(council_member)
        nomination.objection_window_closes_at = timezone.now() - timedelta(seconds=1)
        nomination.save(update_fields=["objection_window_closes_at"])

        client.force_login(leader)
        client.post(f"/council/nominations/{nomination.pk}/confirm/")
        nomination.refresh_from_db()
        invite = nomination.invite_link
        assert invite is not None

        accept_client = Client()
        accept_client.post(invite.get_absolute_url(), follow=True)
        new_user = get_user_model().objects.get(email="newlead@example.com")
        assert new_user.groups.filter(name=COUNCIL_GROUP_NAME).exists()
        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.ACCEPTED_PENDING_ONBOARDING

        # Skip the emailed login-code step (allauth's own concern, not ours)
        # and go straight to completing the onboarding survey.
        accept_client.force_login(new_user)
        mail.outbox.clear()
        response = accept_client.post(
            "/onboarding/",
            {
                "display_name": "New Lead",
                "member_type": get_user_model().MEMBER,
                "country": "US",
                "photo": make_headshot(),
            },
        )
        assert response.status_code == 302, response.content.decode()

        new_user.refresh_from_db()
        assert new_user.onboarding_completed_at is not None
        leader_entry = Leader.objects.get(user=new_user)
        assert leader_entry.photo is not None

        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.ACCEPTED
        assert nomination.announcement_page is not None
        assert nomination.announcement_page.live is False
        assert nomination.announcement_page.featured_image_id == leader_entry.photo_id

        assert len(mail.outbox) == 1
        assert mail.outbox[0].bcc == [onboarding_member.email]

    def test_onboarding_without_a_photo_does_not_finish_the_nomination_yet(
        self, client, leader, council_member, onboarding_member, bootstrapped_site
    ):
        nomination = make_nomination(leader, nominee_email="newlead@example.com", nominee_name="New Lead")
        nomination.second(council_member)
        nomination.objection_window_closes_at = timezone.now() - timedelta(seconds=1)
        nomination.save(update_fields=["objection_window_closes_at"])
        client.force_login(leader)
        client.post(f"/council/nominations/{nomination.pk}/confirm/")
        nomination.refresh_from_db()

        accept_client = Client()
        accept_client.post(nomination.invite_link.get_absolute_url(), follow=True)
        new_user = get_user_model().objects.get(email="newlead@example.com")

        accept_client.force_login(new_user)
        mail.outbox.clear()
        accept_client.post(
            "/onboarding/",
            {"display_name": "New Lead", "member_type": get_user_model().MEMBER, "country": "US"},
        )

        nomination.refresh_from_db()
        assert nomination.status == CouncilNomination.ACCEPTED_PENDING_ONBOARDING
        assert nomination.announcement_page is None
        assert mail.outbox == []
