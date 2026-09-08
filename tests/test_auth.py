"""Auth pages render outside Wagtail, where no `page` is in the context.

These regression-test the template lookups that used to 500 there.
"""

import pytest

pytestmark = pytest.mark.django_db

User = None


@pytest.fixture(autouse=True)
def _load_user_model():
    global User
    from django.contrib.auth import get_user_model

    User = get_user_model()


@pytest.mark.parametrize("path", ["/accounts/login/", "/accounts/signup/"])
def test_auth_pages_render(client, site, path):
    response = client.get(path)
    assert response.status_code == 200
    # Site chrome is present, so these extend the real base template.
    assert "Black Python Devs" in response.content.decode()


def test_auth_page_falls_back_to_default_meta_description(client, site):
    html = client.get("/accounts/login/").content.decode()
    assert "Helping build communities for Black Pythonistas" in html


def test_signup_creates_user_with_generated_username(client, site):
    response = client.post(
        "/accounts/signup/",
        {"email": "member@example.com", "password1": "s3cure-passphrase!", "password2": "s3cure-passphrase!"},
    )
    assert response.status_code in (200, 302)
    user = User.objects.get(email="member@example.com")
    assert user.username, "AccountAdapter should derive a username from the email"


def test_login_uses_email(client, site):
    User.objects.create_user(username="someone", email="someone@example.com", password="s3cure-passphrase!")
    response = client.post(
        "/accounts/login/", {"login": "someone@example.com", "password": "s3cure-passphrase!"}
    )
    assert response.status_code == 302


def test_signup_emails_a_verification_code(client, site):
    from django.core import mail

    response = client.post("/accounts/signup/", {"email": "brandnew@example.com"}, follow=True)
    assert response.redirect_chain[-1][0] == "/accounts/confirm-email/"
    assert "verification code" in mail.outbox[-1].body
    assert "password" not in mail.outbox[-1].body.lower()


def test_signup_with_existing_email_sends_a_login_code_not_a_password_reset(client, site):
    """The site is passwordless: signing up again with a registered address
    should email a sign-in code, never allauth's "reset your password" notice."""
    from django.core import mail

    User.objects.create_user(username="existing", email="existing@example.com", password="unused-pw")
    mail.outbox.clear()

    response = client.post("/accounts/signup/", {"email": "existing@example.com"}, follow=True)

    assert response.redirect_chain[-1][0] == "/accounts/login/code/confirm/"
    body = mail.outbox[-1].body.lower()
    assert "code" in body
    assert "password" not in body
    assert "/accounts/password/reset/" not in body


def test_can_resend_confirmation_code(client, site):
    """A stuck signup can request a fresh code instead of being stuck with an expired one.

    `ACCOUNT_EMAIL_VERIFICATION_SUPPORTS_RESEND` defaults to False, which hides
    the "Request new code" button on the confirm-email page entirely (not just
    rate-limits it) — someone who lets their signup code expire has no way
    back in short of cancelling the stage and starting over.
    """
    from django.core import mail

    client.post("/accounts/signup/", {"email": "pending@example.com"})
    assert len(mail.outbox) == 1
    mail.outbox.clear()

    response = client.post("/accounts/confirm-email/", {"action": "resend"})

    assert response.status_code == 302
    assert len(mail.outbox) == 1
