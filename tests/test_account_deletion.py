"""Self-service account deletion (issue #143).

Members can delete their own account from the member area by typing their
email address to confirm. Staff and superusers are excluded — those accounts
manage CMS content and other members, and deleting the last one can lock
everyone out.
"""

import pytest
from django.core import mail

pytestmark = pytest.mark.django_db

User = None


@pytest.fixture(autouse=True)
def _load_user_model():
    global User
    from django.contrib.auth import get_user_model

    User = get_user_model()


def test_delete_page_requires_sign_in(client, site):
    response = client.get("/members/delete/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_delete_page_renders_for_member(client, site):
    client.force_login(User.objects.create_user(username="member", email="member@example.com"))
    response = client.get("/members/delete/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete your account" in content
    assert "cannot be undone" in content


def test_delete_confirms_with_email(client, site):
    client.force_login(User.objects.create_user(username="member", email="member@example.com"))
    response = client.post("/members/delete/", {"confirm": "member@example.com"}, follow=True)
    assert response.status_code == 200
    assert "Your account has been deleted" in response.content.decode()
    assert not User.objects.filter(email="member@example.com").exists()


def test_delete_confirmation_is_case_insensitive_and_strips_whitespace(client, site):
    client.force_login(User.objects.create_user(username="member", email="member@example.com"))
    response = client.post("/members/delete/", {"confirm": "  Member@Example.com "}, follow=True)
    assert response.status_code == 200
    assert not User.objects.filter(email="member@example.com").exists()


def test_delete_rejects_wrong_confirmation(client, site):
    client.force_login(User.objects.create_user(username="member", email="member@example.com"))
    response = client.post("/members/delete/", {"confirm": "someone-else@example.com"})
    assert response.status_code == 200
    assert "nothing has been deleted" in response.content.decode()
    assert User.objects.filter(email="member@example.com").exists()


def test_deleted_member_is_signed_out(client, site):
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(username="member", email="member@example.com")
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    client.force_login(user)
    client.post("/members/delete/", {"confirm": "member@example.com"})

    # The member page now requires signing in again.
    response = client.get("/members/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_delete_leaves_no_traces_in_related_records(client, site):
    """Deleting the account also removes its direct records — the auth email
    address here — without leaving orphans behind."""
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(username="member", email="member@example.com")
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    client.force_login(user)
    client.post("/members/delete/", {"confirm": "member@example.com"})

    assert not EmailAddress.objects.filter(email="member@example.com").exists()
    # Nothing else was swept up in the cascade.
    assert User.objects.count() == 0


def test_staff_cannot_delete_own_account(client, site):
    client.force_login(User.objects.create_user(username="staffer", email="staffer@example.com", is_staff=True))
    response = client.post("/members/delete/", {"confirm": "staffer@example.com"}, follow=True)
    assert response.status_code == 200
    assert User.objects.filter(email="staffer@example.com").exists()
    # They're bounced back to the member area with an explanation (the
    # apostrophe is HTML-escaped in the rendered message).
    assert "ask another maintainer" in response.content.decode()


def test_superuser_cannot_delete_own_account(client, site):
    client.force_login(User.objects.create_user(username="root", email="root@example.com", is_superuser=True))
    client.post("/members/delete/", {"confirm": "root@example.com"})
    assert User.objects.filter(email="root@example.com").exists()


def test_deleted_email_can_sign_up_again(client, site):
    """After deletion the address is free — a fresh signup works and sends a
    code, rather than tripping over the old account."""
    user = User.objects.create_user(username="member", email="member@example.com")
    client.force_login(user)
    client.post("/members/delete/", {"confirm": "member@example.com"})
    mail.outbox.clear()
    client.logout()

    response = client.post("/accounts/signup/", {"email": "member@example.com"}, follow=True)
    assert response.status_code == 200
    assert User.objects.filter(email="member@example.com").exists()
    assert "verification code" in mail.outbox[-1].body
