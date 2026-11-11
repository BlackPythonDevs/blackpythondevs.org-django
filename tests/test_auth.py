"""Auth pages render outside Wagtail, where no `page` is in the context.

These regression-test the template lookups that used to 500 there.
"""

import hashlib
import re

import pytest
from allauth.core.internal.ratelimit import Rate, get_cache_key
from django.core import mail
from django.core.cache import cache

# allauth renders codes in groups, e.g. "RHBJ-PCTB".
CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")


def extract_code(message):
    match = CODE_RE.search(message.body)
    assert match, f"No code found in email body:\n{message.body}"
    return match.group(1)


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
    response = client.post("/accounts/login/", {"login": "someone@example.com", "password": "s3cure-passphrase!"})
    assert response.status_code == 302


def test_signup_emails_a_verification_code(client, site):
    response = client.post("/accounts/signup/", {"email": "brandnew@example.com"}, follow=True)
    assert response.redirect_chain[-1][0] == "/accounts/confirm-email/"
    assert "verification code" in mail.outbox[-1].body
    assert "password" not in mail.outbox[-1].body.lower()
    user = User.objects.get(email="brandnew@example.com")
    assert not user.has_usable_password(), "Passwordless signup must not set a password"


def test_signup_with_existing_email_sends_a_login_code_not_a_password_reset(client, site):
    """The site is passwordless: signing up again with a registered address
    should email a sign-in code, never allauth's "reset your password" notice."""
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
    client.post("/accounts/signup/", {"email": "pending@example.com"})
    assert len(mail.outbox) == 1
    mail.outbox.clear()

    response = client.post("/accounts/confirm-email/", {"action": "resend"})

    assert response.status_code == 302
    assert len(mail.outbox) == 1


def test_full_signup_then_signin_by_code(client, site):
    mail.outbox.clear()
    client.post("/accounts/signup/", {"email": "member@example.com"})
    code = extract_code(mail.outbox[-1])

    # Confirm the address with the emailed code.
    client.post("/accounts/confirm-email/", {"code": code})

    client.logout()
    mail.outbox.clear()

    # Sign in later with a fresh code — no password anywhere.
    client.post("/accounts/login/code/", {"email": "member@example.com"})
    assert len(mail.outbox) == 1
    login_code = extract_code(mail.outbox[-1])

    client.post("/accounts/login/code/confirm/", {"code": login_code})
    assert client.session.get("_auth_user_id"), "Member should be signed in after code confirmation"


def test_rate_limit_lockout_runbook_clears_only_that_members_key(rf):
    """The README's "too many attempts" runbook must actually unblock one member.

    It clears allauth's per-key ``request_login_code`` counter with a pattern of
    ``allauth:rl:*<sha256(lowercased email)>*``. This pins that pattern to allauth's
    real key format — including the lowercasing — and proves it is scoped to the
    single member: if either drifts, the documented command quietly stops working.
    """
    # Build the cache key allauth uses for the per-email request-login-code throttle.
    request = rf.post("/accounts/login/code/")
    request.META["REMOTE_ADDR"] = "203.0.113.9"
    rate = Rate(1, 60, "key")

    def key_for(email):
        # allauth calls get_cache_key with the lowercased address (forms.py).
        return get_cache_key(request, action="request_login_code", rate=rate, key=email.lower())

    # A mixed-case address on purpose: the digest must be of the lowered form.
    email = "Locked.Member@Example.com"
    locked = key_for(email)
    other = key_for("other@example.com")
    cache.set(locked, [1.0], 60)
    cache.set(other, [1.0], 60)

    digest = hashlib.sha256(email.lower().encode()).hexdigest()
    removed = cache.delete_pattern(f"allauth:rl:*{digest}*")

    assert removed == 1
    assert cache.get(locked) is None
    # Scoped to one digest: an unrelated member keeps their counter.
    assert cache.get(other) is not None
