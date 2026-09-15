"""Messages a community admin sends to BPD leadership.

Recipients are always filtered by the *community's* region, never the sending
admin's own `User.region` — a message is from the community, not from
whichever admin happens to be logged in. See communities/models.py's
docstring for why region uses the users.regions taxonomy specifically.
"""

import base64

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from communities.models import COMMUNITY_ADMIN_GROUP_NAME, Community, CommunityAdmin
from community_messages.models import CommunityMessage
from core.models import LEADERSHIP_GROUP_NAME

# A 1x1 transparent PNG, for the image-upload test.
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def required_groups(db):
    for name in (COMMUNITY_ADMIN_GROUP_NAME, LEADERSHIP_GROUP_NAME):
        Group.objects.get_or_create(name=name)


def make_user(username, **kwargs):
    kwargs.setdefault("onboarding_completed_at", timezone.now())
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="pw", **kwargs
    )


def make_leader(username, country):
    """A user in the Leadership group, with `region` naturally derived from
    `country` (never set directly — it must go through the same derivation
    Community.region does, so the two are comparable)."""
    user = make_user(username, country=country)
    user.groups.add(Group.objects.get(name=LEADERSHIP_GROUP_NAME))
    return user


@pytest.fixture
def community(db):
    return Community.objects.create(name="PyLagos", country="NG")


@pytest.fixture
def admin_user(db, community):
    user = make_user("admin")
    CommunityAdmin.objects.create(community=community, user=user)
    return user


@pytest.fixture
def member(db):
    return make_user("member")


class TestMessageRecipients:
    def test_filters_by_community_region_not_sender_region(self, db, community, admin_user):
        """The sending admin's own User.region must never factor in — only
        the community's region does."""
        admin_user.country = "US"  # a different region than the community's
        admin_user.save()
        matching_leader = make_leader("lead-ng", "NG")  # same country as the community
        other_leader = make_leader("lead-us", "US")

        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Hi", body="Hello")
        recipients = set(message.recipients())

        assert matching_leader in recipients
        assert other_leader not in recipients
        assert admin_user not in recipients  # not in the Leadership group at all

    def test_online_community_reaches_every_region(self, db, admin_user):
        online_community = Community.objects.create(name="Remote Pythonistas", is_online=True)
        CommunityAdmin.objects.create(community=online_community, user=admin_user)
        leader_a = make_leader("lead-a", "NG")
        leader_b = make_leader("lead-b", "US")

        message = CommunityMessage.objects.create(
            community=online_community, sender=admin_user, subject="Hi", body="Hello"
        )
        recipients = set(message.recipients())

        assert leader_a in recipients
        assert leader_b in recipients

    def test_only_leadership_group_members_receive(self, db, community, admin_user):
        make_user("bystander", country="NG")  # same region as the community, but not in Leadership
        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Hi", body="Hello")
        assert message.recipients().count() == 0


class TestSendMessageView:
    def test_admin_can_send_to_matching_leadership(self, client, admin_user, community):
        leader = make_leader("lead-ng", "NG")  # same country as the community
        client.force_login(admin_user)
        response = client.post(
            "/communities/messages/send/",
            {"community": community.pk, "subject": "Update", "body": "Things are happening."},
        )
        assert response.status_code == 302, response.context["form"].errors if response.context else ""
        sent = CommunityMessage.objects.get(subject="Update")
        assert sent.sent_at is not None
        assert sent.recipient_count == 1
        assert len(mail.outbox) == 1
        assert mail.outbox[0].bcc == [leader.email]

    def test_form_only_offers_communities_the_sender_admins(self, client, admin_user, community):
        Community.objects.create(name="Not mine", country="US")
        client.force_login(admin_user)
        response = client.get("/communities/messages/send/")
        assert list(response.context["form"].fields["community"].queryset) == [community]

    def test_non_admin_gets_403(self, client, member):
        client.force_login(member)
        assert client.get("/communities/messages/send/").status_code == 403


class TestMessageDetailView:
    def test_admin_can_read_a_past_message(self, client, admin_user, community):
        message = CommunityMessage.objects.create(
            community=community, sender=admin_user, subject="Update", body="Full details here."
        )
        client.force_login(admin_user)
        response = client.get(f"/communities/messages/{message.pk}/")
        assert response.status_code == 200
        assert "Full details here." in response.content.decode()

    def test_list_links_to_the_detail_page(self, client, admin_user, community):
        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Update", body="x")
        client.force_login(admin_user)
        body = client.get("/communities/messages/").content.decode()
        assert f"/communities/messages/{message.pk}/" in body

    def test_admin_of_a_different_community_gets_404(self, client, admin_user, community):
        other_admin = make_user("other-admin")
        other_community = Community.objects.create(name="Not mine", country="US")
        CommunityAdmin.objects.create(community=other_community, user=other_admin)
        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Update", body="x")

        client.force_login(other_admin)
        assert client.get(f"/communities/messages/{message.pk}/").status_code == 404

    def test_non_admin_gets_403(self, client, member, community, admin_user):
        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Update", body="x")
        client.force_login(member)
        assert client.get(f"/communities/messages/{message.pk}/").status_code == 403


class TestMarkdownAndImages:
    """The composer is shared with notifications' — same markdown pipeline
    and image-upload handling, see templates/includes/message_composer_*."""

    def test_body_is_rendered_from_markdown_in_the_html_alternative(self, client, admin_user, community):
        make_leader("lead-ng", "NG")
        client.force_login(admin_user)
        response = client.post(
            "/communities/messages/send/",
            {
                "community": community.pk,
                "subject": "Update",
                "body": "Check out our **new** [site](https://example.com).",
            },
        )
        assert response.status_code == 302

        sent_message = CommunityMessage.objects.get()
        assert "<strong>new</strong>" in sent_message.body_html
        assert '<a href="https://example.com">site</a>' in sent_message.body_html

        sent = mail.outbox[0]
        assert sent.body == sent_message.body  # plain-text fallback stays raw Markdown
        html_alternative = next(content for content, mimetype in sent.alternatives if mimetype == "text/html")
        assert "<strong>new</strong>" in html_alternative

    def test_uploaded_image_is_appended_to_the_body_as_markdown(self, client, admin_user, community):
        client.force_login(admin_user)
        image = SimpleUploadedFile("logo.png", ONE_PIXEL_PNG, content_type="image/png")
        response = client.post(
            "/communities/messages/send/",
            {"community": community.pk, "subject": "Update", "body": "Photos from the meetup:", "image": image},
        )
        assert response.status_code == 302

        sent_message = CommunityMessage.objects.get()
        assert "![](http://testserver/media/images/logo" in sent_message.body
        assert "<img" in sent_message.body_html

    def test_no_image_leaves_the_body_untouched(self, client, admin_user, community):
        client.force_login(admin_user)
        response = client.post(
            "/communities/messages/send/",
            {"community": community.pk, "subject": "Update", "body": "Nothing to see here."},
        )
        assert response.status_code == 302
        assert CommunityMessage.objects.get().body == "Nothing to see here."
