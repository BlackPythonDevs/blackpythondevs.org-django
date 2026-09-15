"""Broadcast notifications: who can send them, what each sender can filter by,
and who actually receives the email.

Access follows the same shape as nominations: gated on membership of the
"Sponsors" / "Community Partners" groups (or staff/Executor), not on model
permissions. A signed-in member outside those groups gets a 403, not a login
redirect.
"""

import base64

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from notifications.models import (
    COMMUNITY_PARTNER_GROUP_NAME,
    SPONSOR_GROUP_NAME,
    Notification,
)

# A 1x1 transparent PNG, for tests that need a real (if tiny) uploaded image.
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def sender_groups(db):
    for name in ("Executor", SPONSOR_GROUP_NAME, COMMUNITY_PARTNER_GROUP_NAME):
        Group.objects.get_or_create(name=name)


def make_user(username, group=None, **kwargs):
    kwargs.setdefault("onboarding_completed_at", timezone.now())
    user = get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="pw", **kwargs
    )
    if group:
        user.groups.add(Group.objects.get(name=group))
    return user


@pytest.fixture
def staff_member(db):
    return make_user("staffer", is_staff=True)


@pytest.fixture
def executor(db):
    return make_user("executor", "Executor")


@pytest.fixture
def sponsor(db):
    return make_user("sponsor", SPONSOR_GROUP_NAME, region="Northern America")


@pytest.fixture
def community_partner(db):
    return make_user("partner", COMMUNITY_PARTNER_GROUP_NAME, subcommunities=["latam"])


@pytest.fixture
def plain_member(db):
    return make_user("member")


FORM_DATA = {"subject": "Hello", "body": "Just saying hi."}


class TestAccess:
    @pytest.mark.parametrize("path", ["/notifications/", "/notifications/new/"])
    def test_anonymous_is_redirected_to_login(self, client, path):
        response = client.get(path)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    @pytest.mark.parametrize("path", ["/notifications/", "/notifications/new/"])
    def test_plain_member_is_forbidden(self, client, plain_member, path):
        client.force_login(plain_member)
        assert client.get(path).status_code == 403

    @pytest.mark.parametrize(
        "fixture", ["staff_member", "executor", "sponsor", "community_partner"]
    )
    def test_permitted_senders_get_in(self, client, request, fixture):
        client.force_login(request.getfixturevalue(fixture))
        assert client.get("/notifications/new/").status_code == 200

    def test_superuser_gets_in(self, client, db):
        admin = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="pw"
        )
        client.force_login(admin)
        assert client.get("/notifications/new/").status_code == 200


class TestFormRestrictions:
    def test_staff_sees_every_filter(self, client, staff_member):
        client.force_login(staff_member)
        html = client.get("/notifications/new/").content.decode()
        assert 'name="regions"' in html
        assert 'name="roles"' in html
        assert 'name="affinities"' in html

    def test_sponsor_only_sees_regions(self, client, sponsor):
        client.force_login(sponsor)
        html = client.get("/notifications/new/").content.decode()
        assert 'name="regions"' in html
        assert 'name="roles"' not in html
        assert 'name="affinities"' not in html

    def test_community_partner_only_sees_their_own_affinities(self, client, community_partner):
        client.force_login(community_partner)
        html = client.get("/notifications/new/").content.decode()
        assert 'name="regions"' not in html
        assert 'name="roles"' not in html
        assert 'name="affinities"' in html
        # Only their own subcommunity is offered, not the others.
        assert "LATAM" in html
        assert "Pacific Islander" not in html

    def test_community_partner_must_pick_an_affinity(self, client, community_partner):
        client.force_login(community_partner)
        response = client.post("/notifications/new/", FORM_DATA)
        assert response.status_code == 200
        assert Notification.objects.count() == 0

    def test_community_partner_cannot_post_someone_elses_affinity(self, client, community_partner):
        client.force_login(community_partner)
        response = client.post("/notifications/new/", {**FORM_DATA, "affinities": ["pacific_islander"]})
        assert response.status_code == 200
        assert Notification.objects.count() == 0

    def test_sponsor_cannot_smuggle_a_role_filter(self, client, sponsor):
        """Posting a field the sponsor's form doesn't render is just ignored."""
        executor_group = Group.objects.get(name="Executor")
        client.force_login(sponsor)
        response = client.post(
            "/notifications/new/", {**FORM_DATA, "roles": [executor_group.pk]}
        )
        assert response.status_code == 302
        assert Notification.objects.get().roles.count() == 0


class TestSending:
    def test_no_filters_reaches_every_active_member(self, client, staff_member, plain_member):
        client.force_login(staff_member)
        response = client.post("/notifications/new/", FORM_DATA)
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert notification.sent_at is not None
        assert notification.recipient_count == 2  # staff_member + plain_member
        assert len(mail.outbox) == 1
        assert set(mail.outbox[0].bcc) == {staff_member.email, plain_member.email}

    def test_region_filter_narrows_recipients(self, client, staff_member, sponsor):
        other = make_user("other", region="Western Africa")
        client.force_login(staff_member)
        response = client.post("/notifications/new/", {**FORM_DATA, "regions": ["Northern America"]})
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert notification.recipient_count == 1
        assert mail.outbox[0].bcc == [sponsor.email]
        assert other.email not in mail.outbox[0].bcc

    def test_role_filter_narrows_recipients(self, client, staff_member, executor, plain_member):
        client.force_login(staff_member)
        executor_group = Group.objects.get(name="Executor")
        response = client.post(
            "/notifications/new/", {**FORM_DATA, "roles": [executor_group.pk]}
        )
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert notification.recipient_count == 1
        assert mail.outbox[0].bcc == [executor.email]

    def test_sponsor_send_is_scoped_to_their_region_choice(self, client, sponsor, staff_member):
        make_user("other_region_member", region="Eastern Europe")
        client.force_login(sponsor)
        response = client.post("/notifications/new/", {**FORM_DATA, "regions": ["Northern America"]})
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert notification.sender == sponsor
        assert notification.recipient_count == 1
        assert mail.outbox[0].bcc == [sponsor.email]

    def test_community_partner_send_reaches_only_their_affinity(self, client, community_partner):
        other_affinity_member = make_user("other_affinity", subcommunities=["pacific_islander"])
        client.force_login(community_partner)
        response = client.post("/notifications/new/", {**FORM_DATA, "affinities": ["latam"]})
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert notification.recipient_count == 1
        assert mail.outbox[0].bcc == [community_partner.email]
        assert other_affinity_member.email not in mail.outbox[0].bcc

    def test_no_matches_sends_nothing(self, client, staff_member):
        # staff_member has no region set, so filtering on one matches nobody.
        client.force_login(staff_member)
        response = client.post("/notifications/new/", {**FORM_DATA, "regions": ["Antarctica"]})
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert notification.recipient_count == 0
        assert len(mail.outbox) == 0


class TestMarkdownAndImages:
    def test_body_is_rendered_from_markdown_in_the_html_alternative(self, client, staff_member):
        client.force_login(staff_member)
        response = client.post(
            "/notifications/new/", {**FORM_DATA, "body": "Check out our **new** [site](https://example.com)."}
        )
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert "<strong>new</strong>" in notification.body_html
        assert '<a href="https://example.com">site</a>' in notification.body_html

        sent = mail.outbox[0]
        assert sent.body == notification.body  # plain-text fallback stays raw Markdown
        html_alternative = next(content for content, mimetype in sent.alternatives if mimetype == "text/html")
        assert "<strong>new</strong>" in html_alternative

    def test_uploaded_image_is_appended_to_the_body_as_markdown(self, client, staff_member):
        client.force_login(staff_member)
        image = SimpleUploadedFile("logo.png", ONE_PIXEL_PNG, content_type="image/png")
        response = client.post("/notifications/new/", {**FORM_DATA, "image": image})
        assert response.status_code == 302

        notification = Notification.objects.get()
        assert "![](http://testserver/media/images/logo" in notification.body
        assert "<img" in notification.body_html

    def test_no_image_leaves_the_body_untouched(self, client, staff_member):
        client.force_login(staff_member)
        response = client.post("/notifications/new/", FORM_DATA)
        assert response.status_code == 302

        assert Notification.objects.get().body == FORM_DATA["body"]
