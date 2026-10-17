"""Broadcast notifications: who can send them, what each sender can filter by,
and who actually receives the email.

Access follows the same shape as nominations: gated on membership of the
"Sponsors" / "Community Partners" groups (or staff/Executor), not on model
permissions. A signed-in member outside those groups gets a 403, not a login
redirect.
"""

import base64

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from notifications.models import (
    COMMUNITY_PARTNER_GROUP_NAME,
    SPONSOR_GROUP_NAME,
    Notification,
    UserNotification,
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


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", email="root@example.com", password="pw")


FORM_DATA = {"subject": "Hello", "body": "Just saying hi."}


class TestAccess:
    # /notifications/ is the member inbox now (issue #133) — login-required,
    # not sender-gated — so the sender-gated paths are /sent/ and /new/. The
    # old /notifications/inbox/ path redirects first, so it isn't listed here.
    @pytest.mark.parametrize("path", ["/notifications/", "/notifications/sent/", "/notifications/new/"])
    def test_anonymous_is_redirected_to_login(self, client, path):
        response = client.get(path)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    @pytest.mark.parametrize("path", ["/notifications/sent/", "/notifications/new/"])
    def test_plain_member_is_forbidden(self, client, plain_member, path):
        client.force_login(plain_member)
        assert client.get(path).status_code == 403

    @pytest.mark.parametrize("fixture", ["staff_member", "executor", "sponsor", "community_partner", "superuser"])
    def test_permitted_senders_get_in(self, client, request, fixture):
        client.force_login(request.getfixturevalue(fixture))
        assert client.get("/notifications/new/").status_code == 200
        assert client.get("/notifications/sent/").status_code == 200

    def test_plain_member_sees_their_inbox_at_notifications_root(self, client, plain_member):
        """Issue #133: /notifications/ is the member's own inbox, not the
        sender-facing broadcast archive, and any signed-in member can open it."""
        client.force_login(plain_member)
        response = client.get("/notifications/")
        assert response.status_code == 200
        assert "Your notifications" in response.content.decode()

    def test_old_inbox_url_redirects_to_the_inbox(self, client, plain_member):
        client.force_login(plain_member)
        response = client.get("/notifications/inbox/")
        assert response.status_code == 302
        assert response["Location"] == "/notifications/"


class TestSentList:
    """The sender-facing archive of broadcasts, moved to /sent/ (issue #133)."""

    def test_lists_sent_notifications_with_links_to_each(self, client, staff_member):
        client.force_login(staff_member)
        client.post("/notifications/new/", FORM_DATA)
        notification = Notification.objects.get()

        response = client.get("/notifications/sent/")
        content = response.content.decode()
        assert notification.subject in content
        assert f'href="/notifications/{notification.pk}/"' in content


class TestFormRestrictions:
    @pytest.mark.parametrize(
        "fixture,expected_present,expected_absent",
        [
            ("staff_member", {"regions", "roles", "affinities"}, set()),
            ("sponsor", {"regions"}, {"roles", "affinities"}),
            ("community_partner", {"affinities"}, {"regions", "roles"}),
        ],
        ids=["staff_sees_every_filter", "sponsor_only_sees_regions", "community_partner_only_sees_affinities"],
    )
    def test_role_sees_only_its_own_filters(self, client, request, fixture, expected_present, expected_absent):
        client.force_login(request.getfixturevalue(fixture))
        html = client.get("/notifications/new/").content.decode()
        for field in expected_present:
            assert f'name="{field}"' in html
        for field in expected_absent:
            assert f'name="{field}"' not in html

    def test_community_partner_only_sees_their_own_affinities(self, client, community_partner):
        client.force_login(community_partner)
        html = client.get("/notifications/new/").content.decode()
        # Only their own subcommunity is offered, not the others.
        assert "LATAM" in html
        assert "Pacific Islander" not in html

    @pytest.mark.parametrize(
        "extra",
        [{}, {"affinities": ["pacific_islander"]}],
        ids=["no_affinity_picked", "someone_elses_affinity"],
    )
    def test_community_partner_invalid_affinity_is_rejected(self, client, community_partner, extra):
        client.force_login(community_partner)
        response = client.post("/notifications/new/", {**FORM_DATA, **extra})
        assert response.status_code == 200
        assert Notification.objects.count() == 0

    def test_sponsor_cannot_smuggle_a_role_filter(self, client, sponsor):
        """Posting a field the sponsor's form doesn't render is just ignored."""
        executor_group = Group.objects.get(name="Executor")
        client.force_login(sponsor)
        response = client.post("/notifications/new/", {**FORM_DATA, "roles": [executor_group.pk]})
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
        response = client.post("/notifications/new/", {**FORM_DATA, "roles": [executor_group.pk]})
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


class TestInboxEntries:
    """Every recipient gets an inbox entry linking to the on-site detail page
    (issue #133) — before, broadcasts lived only in email, so a member's inbox
    showed nothing for an announcement sent to them."""

    def test_each_recipient_gets_an_inbox_entry(self, client, staff_member, plain_member):
        client.force_login(staff_member)
        client.post("/notifications/new/", FORM_DATA)
        notification = Notification.objects.get()

        entry = UserNotification.objects.get(recipient=plain_member)
        assert entry.message == notification.subject
        assert entry.url == f"/notifications/{notification.pk}/"
        assert entry.is_read is False

        # The sending staff member matched their own no-filter broadcast too.
        assert UserNotification.objects.filter(recipient=staff_member).count() == 1

    def test_non_recipient_gets_no_inbox_entry(self, client, staff_member):
        outsider = make_user("outsider", region="Western Africa")
        client.force_login(staff_member)
        client.post("/notifications/new/", {**FORM_DATA, "regions": ["Northern America"]})

        assert UserNotification.objects.filter(recipient=outsider).exists() is False

    def test_inbox_entry_links_to_a_viewable_detail_page(self, client, staff_member, plain_member):
        client.force_login(staff_member)
        client.post("/notifications/new/", FORM_DATA)

        client.force_login(plain_member)
        entry = UserNotification.objects.get(recipient=plain_member)
        response = client.get(entry.url)
        assert response.status_code == 200
        assert "Just saying hi." in response.content.decode()

    def test_inbox_entry_shows_up_in_the_members_inbox_html(self, client, staff_member, plain_member):
        client.force_login(staff_member)
        client.post("/notifications/new/", FORM_DATA)

        client.force_login(plain_member)
        content = client.get("/notifications/").content.decode()
        assert Notification.objects.get().subject in content


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
        # Plain text wraps the raw Markdown source with the preamble/footer
        # (issue #132) rather than replacing it.
        assert notification.body in sent.body
        assert f"This is a Notification sent by {notification.sender} via BlackPythonDevs.org" in sent.body
        assert f"You can view the notification at: {notification.view_url}" in sent.body
        assert "replies to these messages are automatically deleted" in sent.body
        html_alternative = next(content for content, mimetype in sent.alternatives if mimetype == "text/html")
        assert "<strong>new</strong>" in html_alternative
        assert f'href="{notification.view_url}"' in html_alternative
        assert "replies to these messages are automatically deleted" in html_alternative

    def test_view_url_points_at_the_detail_page(self, client, staff_member):
        client.force_login(staff_member)
        client.post("/notifications/new/", FORM_DATA)

        notification = Notification.objects.get()
        assert notification.view_url == f"{settings.WAGTAILADMIN_BASE_URL}/notifications/{notification.pk}/"
        # And the page it points at exists for a recipient.
        plain_member = make_user("viewer")
        client.force_login(plain_member)
        assert client.get(f"/notifications/{notification.pk}/").status_code == 200

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


class TestDetailPage:
    """The on-site page notification emails link to (issue #132)."""

    def make_notification(self, **kwargs):
        sender = make_user("sender", is_staff=True)
        return Notification.objects.create(sender=sender, **kwargs)

    def test_anonymous_is_redirected_to_login(self, client):
        notification = self.make_notification(subject="Hi", body="Body.")
        response = client.get(f"/notifications/{notification.pk}/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_recipient_can_view(self, client, staff_member, plain_member):
        client.force_login(staff_member)
        client.post("/notifications/new/", FORM_DATA)
        notification = Notification.objects.get()

        client.force_login(plain_member)
        response = client.get(f"/notifications/{notification.pk}/")
        assert response.status_code == 200
        assert "Just saying hi." in response.content.decode()

    def test_member_outside_the_filters_gets_a_404(self, client, staff_member):
        """A member the announcement wasn't sent to can't read it by guessing
        the URL — sponsors' announcements shouldn't leak to non-targeted
        members."""
        client.force_login(staff_member)
        client.post("/notifications/new/", {**FORM_DATA, "affinities": ["latam"]})
        notification = Notification.objects.get()

        outsider = make_user("outsider")
        client.force_login(outsider)
        assert client.get(f"/notifications/{notification.pk}/").status_code == 404

    def test_senders_and_staff_can_view(self, client, staff_member, sponsor):
        client.force_login(staff_member)
        client.post("/notifications/new/", {**FORM_DATA, "regions": ["Western Africa"]})
        notification = Notification.objects.get()

        # The sponsor doesn't match the region filter, but senders can view.
        client.force_login(sponsor)
        assert client.get(f"/notifications/{notification.pk}/").status_code == 200
