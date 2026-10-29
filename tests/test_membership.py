"""The passwordless membership flow and the Discord connection.

Members sign up with an email only, receive a code, and sign in with it.
Discord is never a sign-in method — it is connected afterwards to obtain the
role that permits posting in the community server.
"""

import pytest
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from communities.models import Community, CommunityAdmin
from community_messages.models import CommunityMessage
from core.models import COUNCIL_GROUP_NAME, EXECUTOR_GROUP_NAME

pytestmark = pytest.mark.django_db


class TestPasswordlessSignup:
    def test_signup_form_has_no_password_fields(self, client, site):
        html = client.get("/accounts/signup/").content.decode()
        assert 'name="email"' in html
        assert 'name="password1"' not in html
        assert 'name="password2"' not in html

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

    def test_page_links_to_the_coc_report_form(self, client, site):
        html = client.get("/become-a-member/").content.decode()
        assert "/coc/report/" in html


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


class TestStudentAmbassadorVisibility:
    def test_hidden_for_a_member_without_the_student_group(self, client, site, member):
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "Student Ambassador programme" not in html

    def test_shown_for_a_member_in_the_student_group(self, client, site, member):
        from django.contrib.auth.models import Group

        from core.models import STUDENT_GROUP_NAME

        member.groups.add(Group.objects.get(name=STUDENT_GROUP_NAME))
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "Student Ambassador programme" in html
        assert "Apply now" in html

    def test_shown_for_a_member_with_an_existing_application(self, client, site, member):
        from ambassadors.models import StudentAmbassador

        StudentAmbassador.objects.create(
            user=member, name="A Member", email=member.email, school="A School", motivation="Because"
        )
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "Student Ambassador programme" in html
        assert "Your application status" in html


class _FakeDiscordResponse:
    def __init__(self, status_code=201, text=""):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def configured_discord_settings(settings):
    settings.DISCORD_GUILD_ID = "1"
    settings.DISCORD_BOT_TOKEN = "token"
    settings.DISCORD_MEMBER_ROLE_ID = "42"


class TestDiscordRoleGrant:
    def test_not_configured_by_default(self):
        from users.discord import is_configured

        assert is_configured() is False

    def test_grant_adds_member_with_role(self, monkeypatch, configured_discord_settings):
        from users import discord

        calls = {}

        def fake_put(url, headers=None, json=None, timeout=None):
            calls["url"] = url
            calls["json"] = json
            return _FakeDiscordResponse(201)

        monkeypatch.setattr(discord.requests, "put", fake_put)
        assert discord.grant_member_access("999", "access-token") == "added"
        assert calls["json"]["roles"] == ["42"]
        assert calls["json"]["access_token"] == "access-token"

    def test_existing_member_gets_role_applied_separately(self, monkeypatch, configured_discord_settings):
        """A 204 means they were already in the guild, so `roles` was ignored."""
        from users import discord

        urls = []

        def fake_put(url, headers=None, json=None, timeout=None):
            urls.append(url)
            return _FakeDiscordResponse(204)

        monkeypatch.setattr(discord.requests, "put", fake_put)
        assert discord.grant_member_access("999", "access-token") == "role_granted"
        assert len(urls) == 2
        assert urls[1].endswith("/roles/42")

    def test_network_failure_does_not_raise(self, monkeypatch, configured_discord_settings):
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


class TestCommandCenter:
    """Council members and above — plus community admins — get the compact
    command-center dashboard instead of the regular member page (issue #174)."""

    @pytest.fixture
    def council_member(self, db):
        user = get_user_model().objects.create_user(
            username="councilor",
            email="councilor@example.com",
            display_name="Cee Member",
            onboarding_completed_at=timezone.now(),
        )
        user.groups.add(Group.objects.get(name=COUNCIL_GROUP_NAME))
        return user

    @pytest.fixture
    def community_admin(self, db):
        user = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            onboarding_completed_at=timezone.now(),
        )
        community = Community.objects.create(name="PyLagos", country="NG")
        CommunityAdmin.objects.create(community=community, user=user)
        return user

    def test_council_member_gets_the_command_center(self, client, site, council_member):
        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert "command-center" in html
        assert "Cee Member" in html

    def test_executor_gets_the_command_center(self, client, site):
        user = get_user_model().objects.create_user(
            username="executor",
            email="executor@example.com",
            onboarding_completed_at=timezone.now(),
        )
        user.groups.add(Group.objects.get(name=EXECUTOR_GROUP_NAME))
        client.force_login(user)
        assert "command-center" in client.get("/members/").content.decode()

    def test_community_admin_gets_the_command_center(self, client, site, community_admin):
        client.force_login(community_admin)
        html = client.get("/members/").content.decode()
        assert "command-center" in html
        assert "Your communities" in html

    def test_regular_member_keeps_the_plain_member_page(self, client, site, member):
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "command-center" not in html
        assert "Your account" in html

    def test_member_area_links_to_the_coc_report_form(self, client, site, member):
        client.force_login(member)
        html = client.get("/members/").content.decode()
        assert "/coc/report/" in html

    def test_command_center_links_to_the_coc_report_form(self, client, site, council_member):
        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert "/coc/report/" in html

    def test_messages_preview_lists_recent_community_messages(self, client, site, council_member):
        community = Community.objects.create(name="Remote Pythonistas", is_online=True)
        sender = get_user_model().objects.create_user(username="sender", email="sender@example.com")
        CommunityAdmin.objects.create(community=community, user=sender)
        message = CommunityMessage.objects.create(
            community=community, sender=sender, subject="June meet-up recap", body="All went well."
        )
        message.send()

        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert "June meet-up recap" in html
        assert 'href="/communities/messages/inbox/"' in html

    def test_account_links_stay_available(self, client, site, council_member):
        client.force_login(council_member)
        html = client.get("/members/").content.decode()
        assert 'href="/profile/"' in html
        assert "Sign out" in html
