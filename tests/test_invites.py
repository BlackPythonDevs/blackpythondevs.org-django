"""Staff-generated one-time invite links (users.models.InviteLink).

Covers the admin's privilege-escalation guard (a non-superuser can only bake
in groups they themselves belong to), the accept flow (find-or-create the
account, apply groups, hand off to allauth's login-by-code — same handoff
users.forms.SignupForm uses for an existing member), and that a link stops
working once it's used or past its expiry.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from users.models import InviteLink

pytestmark = pytest.mark.django_db

User = get_user_model()


def make_user(username, is_staff=False, is_superuser=False, groups=()):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pw",
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    for name in groups:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


@pytest.fixture
def executor_group(db):
    group, _ = Group.objects.get_or_create(name="Executor")
    return group


@pytest.fixture
def staff_user():
    return make_user("staffer", is_staff=True)


@pytest.fixture
def executor_staff(executor_group):
    return make_user("execstaff", is_staff=True, groups=["Executor"])


@pytest.fixture
def superuser():
    return make_user("root", is_staff=True, is_superuser=True)


def make_invite(email="invitee@example.com", groups=(), created_by=None, **kwargs):
    invite = InviteLink.objects.create(email=email, created_by=created_by, **kwargs)
    invite.groups.set(groups)
    return invite


class TestInviteLinkModel:
    def test_valid_invite_is_neither_used_nor_expired(self, staff_user):
        invite = make_invite(created_by=staff_user)
        assert invite.is_valid
        assert not invite.is_used
        assert not invite.is_expired

    def test_expired_invite_is_invalid(self, staff_user):
        invite = make_invite(created_by=staff_user, expires_at=timezone.now() - timedelta(seconds=1))
        assert invite.is_expired
        assert not invite.is_valid

    def test_used_invite_is_invalid(self, staff_user):
        invite = make_invite(created_by=staff_user, used_at=timezone.now())
        assert invite.is_used
        assert not invite.is_valid

    def test_accept_creates_a_new_account_with_groups_applied(self, staff_user, executor_group, rf):
        invite = make_invite(created_by=staff_user, groups=[executor_group])
        request = rf.post(invite.get_absolute_url())

        user = invite.accept(request)

        assert user.email == invite.email
        assert user.username, "AccountAdapter should still derive a username"
        assert list(user.groups.values_list("name", flat=True)) == ["Executor"]
        invite.refresh_from_db()
        assert invite.used_at is not None
        assert invite.accepted_by == user

    def test_accept_adds_groups_to_an_existing_account(self, staff_user, executor_group, rf):
        existing = make_user("already-here")
        invite = make_invite(email=existing.email, created_by=staff_user, groups=[executor_group])
        request = rf.post(invite.get_absolute_url())

        user = invite.accept(request)

        assert user.pk == existing.pk
        assert User.objects.filter(email=existing.email).count() == 1
        assert user.groups.filter(name="Executor").exists()


class TestInviteAcceptView:
    def test_valid_invite_shows_confirmation(self, client, site, staff_user):
        invite = make_invite(created_by=staff_user)
        response = client.get(invite.get_absolute_url())
        assert response.status_code == 200
        assert invite.email in response.content.decode()

    def test_unknown_token_404s(self, client, site):
        response = client.get("/invite/does-not-exist/")
        assert response.status_code == 404

    def test_expired_invite_shows_invalid_state_and_refuses_get(self, client, site, staff_user):
        invite = make_invite(created_by=staff_user, expires_at=timezone.now() - timedelta(seconds=1))
        response = client.get(invite.get_absolute_url())
        assert response.status_code == 200
        assert "expired" in response.content.decode().lower()

    def test_accepting_creates_account_sends_login_code_and_redirects(self, client, site, staff_user, executor_group):
        invite = make_invite(created_by=staff_user, groups=[executor_group])
        mail.outbox.clear()

        response = client.post(invite.get_absolute_url(), follow=True)

        assert response.redirect_chain[-1][0] == "/accounts/login/code/confirm/"
        user = User.objects.get(email=invite.email)
        assert user.groups.filter(name="Executor").exists()
        assert "code" in mail.outbox[-1].body.lower()

    def test_link_is_single_use(self, client, site, staff_user):
        invite = make_invite(created_by=staff_user)
        client.post(invite.get_absolute_url())

        response = client.get(invite.get_absolute_url())

        assert response.status_code == 200
        assert "already been used" in response.content.decode()

        second_attempt = client.post(invite.get_absolute_url())
        # A used invite must not be accepted twice.
        assert second_attempt.status_code == 200
        assert User.objects.filter(email=invite.email).count() == 1


class TestInviteLinkAdminGroupRestriction:
    """A non-superuser staff member can only bake in groups they belong to."""

    def test_superuser_can_grant_any_group(self, client, superuser, executor_group):
        other_group, _ = Group.objects.get_or_create(name="Sponsors")
        client.force_login(superuser)

        client.post(
            "/django-admin/users/invitelink/add/",
            {"email": "new@example.com", "groups": [executor_group.pk, other_group.pk]},
            follow=True,
        )

        invite = InviteLink.objects.get(email="new@example.com")
        assert set(invite.groups.values_list("name", flat=True)) == {"Executor", "Sponsors"}
        assert invite.created_by == superuser

    def test_non_superuser_cannot_grant_a_group_they_lack(self, client, executor_staff):
        Group.objects.get_or_create(name="Sponsors")
        client.force_login(executor_staff)

        response = client.get("/django-admin/users/invitelink/add/")
        form = response.context["adminform"].form
        allowed = set(form.fields["groups"].queryset.values_list("name", flat=True))

        assert allowed == {"Executor"}
        assert "Sponsors" not in allowed


def test_admin_homepage_has_an_invite_button(client, staff_user):
    client.force_login(staff_user)

    response = client.get("/django-admin/")

    assert response.status_code == 200
    assert reverse("admin:users_invitelink_add") in response.content.decode()


class TestInviteLinkAdminCopyButton:
    def test_creating_an_invite_shows_a_copy_button_for_it(self, client, staff_user):
        client.force_login(staff_user)

        response = client.post(
            "/django-admin/users/invitelink/add/", {"email": "copyme@example.com", "groups": []}, follow=True
        )

        invite = InviteLink.objects.get(email="copyme@example.com")
        html = response.content.decode()
        assert "invite-copy-button" in html
        assert invite.get_absolute_url() in html

    def test_change_form_shows_a_copy_button_for_the_link(self, client, staff_user):
        invite = make_invite(created_by=staff_user)
        client.force_login(staff_user)

        response = client.get(f"/django-admin/users/invitelink/{invite.pk}/change/")

        html = response.content.decode()
        assert "invite-copy-button" in html
        assert invite.get_absolute_url() in html
