"""The passwordless membership flow and the Discord connection.

Members sign up with an email only, receive a code, and sign in with it.
Discord is never a sign-in method — it is connected afterwards to obtain the
role that permits posting in the community server.
"""

import re

import pytest
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone

pytestmark = pytest.mark.django_db

# allauth renders codes in groups, e.g. "RHBJ-PCTB".
CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")


def extract_code(message):
    match = CODE_RE.search(message.body)
    assert match, f"No code found in email body:\n{message.body}"
    return match.group(1)


class TestPasswordlessSignup:
    def test_signup_form_has_no_password_fields(self, client, site):
        html = client.get("/accounts/signup/").content.decode()
        assert 'name="email"' in html
        assert 'name="password1"' not in html
        assert 'name="password2"' not in html

    def test_signup_sends_a_code_and_creates_an_unusable_password(self, client, site):
        mail.outbox.clear()
        response = client.post("/accounts/signup/", {"email": "newbie@example.com"})
        assert response.status_code in (200, 302)

        user = get_user_model().objects.get(email="newbie@example.com")
        assert not user.has_usable_password(), "Passwordless signup must not set a password"
        assert user.username, "Adapter should derive a username from the email"
        assert len(mail.outbox) == 1

    def test_full_signup_then_signin_by_code(self, client, site):
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

    def test_login_page_offers_a_code_not_a_password(self, client, site):
        html = client.get("/accounts/login/").content.decode()
        assert "code" in html.lower()
        assert 'type="password"' not in html


class TestMembershipPage:
    @pytest.fixture
    def site(self, site):
        from home.models import MembershipPage

        page = MembershipPage(title="Become a Member", slug="become-a-member")
        site.add_child(instance=page)
        page.save_revision().publish()
        return site

    def test_page_renders_with_signup_form(self, client, site):
        html = client.get("/become-a-member/").content.decode()
        assert 'action="/accounts/signup/"' in html
        assert 'name="email"' in html

    def test_page_does_not_offer_discord_as_signup(self, client, site):
        html = client.get("/become-a-member/").content.decode()
        assert "/accounts/discord/login/" not in html

    def test_signed_in_member_sees_member_area_link(self, client, site, member):
        client.force_login(member)
        html = client.get("/become-a-member/").content.decode()
        assert "already a member" in html.lower()


class TestDiscordIsConnectOnly:
    def test_login_page_has_no_discord_button(self, client, site):
        """The footer links to the Discord server; what must be absent is any
        OAuth entry point that would let Discord act as a sign-in method."""
        html = client.get("/accounts/login/").content.decode()
        assert "/accounts/discord/login/" not in html
        assert "process=login" not in html

    def test_discord_cannot_create_an_account(self):
        """The adapter must refuse signup, so Discord can only ever connect."""
        from users.adapters import SocialAccountAdapter

        assert SocialAccountAdapter().is_open_for_signup(None, None) is False

    def test_email_authentication_is_disabled(self):
        """Otherwise a Discord account could match an existing user by email."""
        assert settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION is False
        assert settings.SOCIALACCOUNT_AUTO_SIGNUP is False

    def test_members_area_requires_login(self, client, site):
        response = client.get("/members/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_members_area_offers_discord_connection(self, client, site, member, discord_app):
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "Connect Discord" in html
        assert "process=connect" in html or "connect" in html

    def test_members_area_shows_connected_state(self, client, site, member, discord_app):
        SocialAccount.objects.create(
            user=member, provider="discord", uid="123456789", extra_data={"username": "pythonista"}
        )
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "pythonista" in html
        assert "Connect Discord" not in html


class TestDiscordRoleGrant:
    def test_not_configured_by_default(self):
        from users.discord import is_configured

        assert is_configured() is False

    @override_settings(
        DISCORD_GUILD_ID="1", DISCORD_BOT_TOKEN="token", DISCORD_MEMBER_ROLE_ID="42"
    )
    def test_grant_adds_member_with_role(self, monkeypatch):
        from users import discord

        calls = {}

        class Response:
            status_code = 201
            text = ""

        def fake_put(url, headers=None, json=None, timeout=None):
            calls["url"] = url
            calls["json"] = json
            return Response()

        monkeypatch.setattr(discord.requests, "put", fake_put)
        assert discord.grant_member_access("999", "access-token") == "added"
        assert calls["json"]["roles"] == ["42"]
        assert calls["json"]["access_token"] == "access-token"

    @override_settings(
        DISCORD_GUILD_ID="1", DISCORD_BOT_TOKEN="token", DISCORD_MEMBER_ROLE_ID="42"
    )
    def test_existing_member_gets_role_applied_separately(self, monkeypatch):
        """A 204 means they were already in the guild, so `roles` was ignored."""
        from users import discord

        urls = []

        class Response:
            def __init__(self, status_code):
                self.status_code = status_code
                self.text = ""

        def fake_put(url, headers=None, json=None, timeout=None):
            urls.append(url)
            return Response(204)

        monkeypatch.setattr(discord.requests, "put", fake_put)
        assert discord.grant_member_access("999", "access-token") == "role_granted"
        assert len(urls) == 2
        assert urls[1].endswith("/roles/42")

    @override_settings(
        DISCORD_GUILD_ID="1", DISCORD_BOT_TOKEN="token", DISCORD_MEMBER_ROLE_ID="42"
    )
    def test_network_failure_does_not_raise(self, monkeypatch):
        from users import discord

        def boom(*args, **kwargs):
            raise discord.requests.RequestException("network down")

        monkeypatch.setattr(discord.requests, "put", boom)
        assert discord.grant_member_access("999", "access-token") == "failed"


@pytest.fixture
def member(db):
    # Already onboarded: these tests exercise the member area itself, not
    # the onboarding survey that would otherwise redirect a fresh account.
    return get_user_model().objects.create_user(
        username="member", email="member@example.com", onboarding_completed_at=timezone.now()
    )


@pytest.fixture
def discord_app(db):
    # django.contrib.sites isn't installed, so the app is matched by provider.
    return SocialApp.objects.create(provider="discord", name="Discord", client_id="cid", secret="secret")
