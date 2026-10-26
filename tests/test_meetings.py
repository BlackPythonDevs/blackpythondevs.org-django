"""The leadership meeting-minutes console (meetings.views.MeetingView): a
full-CRUD neapolitan front-end at /leadership/meetings/, with a per-meeting
.ics calendar download.

Mirrors tests/test_sponsor_console.py's access-control pattern, plus the
command-center card that links here (issue #178).
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from meetings.models import Meeting

pytestmark = pytest.mark.django_db

CONSOLE_URLS = ["/leadership/meetings/", "/leadership/meetings/new/"]
DETAIL_URLS = [
    "/leadership/meetings/{pk}/",
    "/leadership/meetings/{pk}/edit/",
    "/leadership/meetings/{pk}/delete/",
    "/leadership/meetings/{pk}/meeting.ics",
]


@pytest.fixture
def meeting(db):
    return Meeting.objects.create(
        title="Leadership sync",
        scheduled_at=timezone.now() + timedelta(days=7),
        location="Discord",
        url="https://meet.example.com/leadership",
        notes="Agenda: budget, elections.",
    )


@pytest.fixture
def leadership_roles(db):
    return {name: Group.objects.get(name=name) for name in ("Leadership Council", "Executor")}


@pytest.fixture
def council_member(db, leadership_roles):
    user = get_user_model().objects.create_user(username="council", email="council@example.com", password="pw")
    user.onboarding_completed_at = timezone.now()
    user.save()
    user.groups.add(leadership_roles["Leadership Council"])
    return user


@pytest.fixture
def member(db):
    user = get_user_model().objects.create_user(username="member", email="member@example.com", password="pw")
    user.onboarding_completed_at = timezone.now()
    user.save()
    return user


def all_urls(meeting):
    return CONSOLE_URLS + [u.format(pk=meeting.pk) for u in DETAIL_URLS]


class TestConsoleAccess:
    @pytest.mark.parametrize(
        "group_name,expected_status",
        [("Leadership Council", 200), ("Executor", 200)],
        ids=["council_member", "executor"],
    )
    def test_leadership_groups_get_in(self, request, client, meeting, group_name, expected_status):
        user = get_user_model().objects.create_user(
            username=f"leader-{group_name}", email="l@example.com", password="pw"
        )
        user.onboarding_completed_at = timezone.now()
        user.save()
        user.groups.add(Group.objects.get(name=group_name))
        client.force_login(user)
        for url in all_urls(meeting):
            assert client.get(url).status_code == expected_status, url

    def test_anonymous_is_sent_to_login(self, client, meeting):
        for url in all_urls(meeting):
            assert client.get(url).status_code == 302, url

    def test_ordinary_member_gets_403(self, client, member, meeting):
        client.force_login(member)
        for url in all_urls(meeting):
            assert client.get(url).status_code == 403, url

    def test_superuser_gets_in(self, client, meeting, django_user_model):
        user = django_user_model.objects.create_user(
            username="root", email="root@example.com", password="pw", is_superuser=True
        )
        user.onboarding_completed_at = timezone.now()
        user.save()
        client.force_login(user)
        for url in all_urls(meeting):
            assert client.get(url).status_code == 200, url


class TestConsoleTemplates:
    def test_site_templates_are_used(self, client, council_member, meeting):
        client.force_login(council_member)
        expected = {
            "/leadership/meetings/": "meetings/meeting_list.html",
            "/leadership/meetings/new/": "meetings/meeting_form.html",
            f"/leadership/meetings/{meeting.pk}/": "meetings/meeting_detail.html",
            f"/leadership/meetings/{meeting.pk}/edit/": "meetings/meeting_form.html",
            f"/leadership/meetings/{meeting.pk}/delete/": "meetings/meeting_confirm_delete.html",
        }
        for url, template in expected.items():
            names = [t.name for t in client.get(url).templates if t.name]
            assert template in names, f"{url} rendered {names}"


class TestConsoleWrites:
    def test_leader_can_create(self, client, council_member):
        client.force_login(council_member)
        response = client.post(
            "/leadership/meetings/new/",
            {
                "title": "February sync",
                "scheduled_at": "2030-02-01 18:00:00",
                "location": "Discord",
                "url": "https://meet.example.com/feb",
                "notes": "First agenda item.",
            },
        )
        assert response.status_code == 302
        assert Meeting.objects.filter(title="February sync").exists()

    def test_leader_can_update(self, client, council_member, meeting):
        client.force_login(council_member)
        response = client.post(
            f"/leadership/meetings/{meeting.pk}/edit/",
            {
                "title": meeting.title,
                "scheduled_at": "2030-03-01 19:00:00",
                "location": meeting.location,
                "url": meeting.url,
                "notes": "Published minutes.",
            },
        )
        assert response.status_code == 302
        meeting.refresh_from_db()
        assert meeting.notes == "Published minutes."

    def test_leader_can_delete(self, client, council_member, meeting):
        client.force_login(council_member)
        response = client.post(f"/leadership/meetings/{meeting.pk}/delete/")
        assert response.status_code == 302
        assert not Meeting.objects.filter(pk=meeting.pk).exists()


class TestICSDownload:
    def test_content_type_and_disposition(self, client, council_member, meeting):
        client.force_login(council_member)
        response = client.get(f"/leadership/meetings/{meeting.pk}/meeting.ics")
        assert response["Content-Type"] == "text/calendar; charset=utf-8"
        assert response["Content-Disposition"].startswith("attachment; filename=")

    def test_calendar_entry_carries_the_meeting(self, client, council_member, meeting):
        client.force_login(council_member)
        body = client.get(f"/leadership/meetings/{meeting.pk}/meeting.ics").content.decode()
        assert "BEGIN:VCALENDAR" in body
        assert "BEGIN:VEVENT" in body
        assert f"UID:meeting-{meeting.pk}@blackpythondevs.org" in body
        assert f"SUMMARY:{meeting.title}" in body
        assert "DESCRIPTION:Agenda: budget\\, elections." in body
        assert f"LOCATION:{meeting.location}" in body
        assert f"URL:{meeting.url}" in body
        # RFC 5545 lines are CRLF-terminated.
        assert body.endswith("END:VCALENDAR\r\n")

    def test_dtstart_is_utc(self, client, council_member, meeting):
        client.force_login(council_member)
        meeting.scheduled_at = datetime(2030, 6, 1, 15, 30, tzinfo=UTC)
        meeting.save()
        body = client.get(f"/leadership/meetings/{meeting.pk}/meeting.ics").content.decode()
        assert "DTSTART:20300601T153000Z" in body


class TestCommandCenterCard:
    def test_leadership_sees_meetings_card(self, client, council_member):
        client.force_login(council_member)
        response = client.get("/members/")
        assert response.status_code == 200
        assert "Leadership meetings" in response.content.decode()
        assert "/leadership/meetings/" in response.content.decode()

    def test_ordinary_member_does_not_see_meetings_card(self, client, member):
        client.force_login(member)
        content = client.get("/members/").content.decode()
        assert "Leadership meetings" not in content
