"""Each member's own in-app notification inbox (notifications.models.
UserNotification, issue #98) — distinct from the broadcast `Notification`
model covered in test_notifications.py. Checklist @mentions
(tests/test_checklists.py) are the first real caller of `notify()`; these
tests exercise the inbox/bell machinery on its own.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from notifications.models import UserNotification, notify

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="alex", email="alex@example.com", password="pw", onboarding_completed_at=timezone.now()
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="sam", email="sam@example.com", password="pw", onboarding_completed_at=timezone.now()
    )


class TestNotifyHelper:
    def test_notify_creates_an_unread_row(self, user, other_user):
        note = notify(user, "sam mentioned you", actor=other_user, url="/somewhere/")

        assert note.recipient == user
        assert note.actor == other_user
        assert note.url == "/somewhere/"
        assert note.is_read is False
        assert note.read_at is None

    def test_mark_read_sets_read_at_once(self, user):
        note = notify(user, "hello")
        note.mark_read()
        first_read_at = note.read_at
        assert first_read_at is not None

        note.mark_read()
        note.refresh_from_db()
        assert note.read_at == first_read_at


class TestNotificationInboxView:
    def test_anonymous_is_redirected(self, client):
        response = client.get("/notifications/inbox/")
        assert response.status_code == 302

    def test_shows_only_the_signed_in_users_own_notifications(self, client, user, other_user):
        mine = notify(user, "for me")
        notify(other_user, "not for me")
        client.force_login(user)

        response = client.get("/notifications/inbox/")
        content = response.content.decode()
        assert mine.message in content
        assert "not for me" not in content

    def test_mark_read_action(self, client, user):
        note = notify(user, "for me")
        client.force_login(user)

        client.post("/notifications/inbox/", {"action": "mark_read", "notification_id": note.pk})

        note.refresh_from_db()
        assert note.is_read is True

    def test_mark_read_cannot_target_another_users_notification(self, client, user, other_user):
        note = notify(other_user, "not yours")
        client.force_login(user)

        client.post("/notifications/inbox/", {"action": "mark_read", "notification_id": note.pk})

        note.refresh_from_db()
        assert note.is_read is False

    def test_mark_all_read_action(self, client, user):
        notify(user, "one")
        notify(user, "two")
        client.force_login(user)

        client.post("/notifications/inbox/", {"action": "mark_all_read"})

        assert not UserNotification.objects.filter(recipient=user, read_at__isnull=True).exists()


class TestNotificationBell:
    def test_shows_unread_count_for_a_signed_in_member(self, client, user):
        notify(user, "one")
        notify(user, "two")
        client.force_login(user)

        content = client.get("/members/").content.decode()
        assert "notification-bell-count" in content
        assert ">2<" in content

    def test_hides_the_count_badge_when_nothing_is_unread(self, client, user):
        client.force_login(user)

        content = client.get("/members/").content.decode()
        assert "notification-bell-count" not in content

    def test_does_not_render_for_an_anonymous_visitor(self, client):
        content = client.get("/accounts/login/").content.decode()
        assert 'href="/notifications/inbox/"' not in content
