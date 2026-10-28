"""The leadership meeting-minutes console (meetings.views.MeetingView): a
full-CRUD neapolitan front-end at /leadership/meetings/, with a per-meeting
.ics calendar download.

Mirrors tests/test_sponsor_console.py's access-control pattern, plus the
command-center card that links here (issue #178).
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from meetings.models import CalendarFeed, Meeting

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


def scheduled_at_input(html):
    """The <input> tag for the scheduled_at field, as rendered."""
    match = re.search(r'<input[^>]*\bname="scheduled_at"[^>]*>', html)
    assert match, "no scheduled_at input rendered"
    return match.group(0)


class TestDateTimePicker:
    def test_scheduled_at_uses_native_datetime_picker(self, client, council_member):
        """The form renders scheduled_at as <input type="datetime-local">,
        not a bare text box (issue #184), and prefills the current value in
        the format the picker expects when editing."""
        client.force_login(council_member)
        new_html = client.get("/leadership/meetings/new/").content.decode()
        assert 'type="datetime-local"' in scheduled_at_input(new_html)

        meeting = Meeting.objects.create(
            title="Picked meeting",
            scheduled_at=datetime(2030, 6, 1, 15, 30, tzinfo=UTC),
        )
        edit_html = client.get(f"/leadership/meetings/{meeting.pk}/edit/").content.decode()
        assert 'type="datetime-local"' in scheduled_at_input(edit_html)
        assert 'value="2030-06-01T15:30"' in scheduled_at_input(edit_html)


class TestConsoleWrites:
    def test_leader_can_create(self, client, council_member):
        client.force_login(council_member)
        response = client.post(
            "/leadership/meetings/new/",
            {
                "title": "February sync",
                "scheduled_at": "2030-02-01T18:30",  # what datetime-local submits
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
                "scheduled_at": "2030-03-01T19:00",  # what datetime-local submits
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


class TestDateTime:
    def test_minutes_render_markdown(self, client, council_member):
        """Notes render as Markdown (headings, lists, tables), not raw source."""
        meeting = Meeting.objects.create(
            title="Markdown minutes",
            scheduled_at=timezone.now() + timedelta(days=1),
            notes="## Decisions\n\n- ship it\n- **soon**\n",
        )
        client.force_login(council_member)
        body = client.get(f"/leadership/meetings/{meeting.pk}/").content.decode()
        assert "<h2>Decisions</h2>" in body
        assert "<li>ship it</li>" in body
        assert "<strong>soon</strong>" in body

    def test_raw_html_in_the_notes_is_stripped_not_rendered(self, client, council_member):
        meeting = Meeting.objects.create(
            title="XSS minutes",
            scheduled_at=timezone.now() + timedelta(days=1),
            notes='Hello <script>alert("x")</script> <img src=x onerror="alert(1)"> world.',
        )
        client.force_login(council_member)
        body = client.get(f"/leadership/meetings/{meeting.pk}/").content.decode()
        # The <script> tag itself is stripped (its inert text content is allowed
        # to remain, same as bleach's own default behaviour) — base.html has its
        # own legitimate <script> (the theme toggle), so check for an actual
        # <script> element wrapping the payload, not just the bare tag anywhere.
        assert "<script>alert" not in body
        assert "onerror" not in body

    def test_empty_notes_show_placeholder(self, client, council_member):
        meeting = Meeting.objects.create(
            title="Empty minutes",
            scheduled_at=timezone.now() + timedelta(days=1),
        )
        client.force_login(council_member)
        body = client.get(f"/leadership/meetings/{meeting.pk}/").content.decode()
        assert "No minutes published yet." in body


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

    def test_past_meeting_is_not_downloadable(self, client, council_member, meeting):
        """Once the meeting has been had, the invite is gone (issue #186):
        the .ics 404s even for leadership."""
        meeting.scheduled_at = timezone.now() - timedelta(hours=1)
        meeting.save()
        client.force_login(council_member)
        assert client.get(f"/leadership/meetings/{meeting.pk}/meeting.ics").status_code == 404

    def test_past_meeting_detail_hides_the_download_button(self, client, council_member, meeting):
        meeting.scheduled_at = timezone.now() - timedelta(hours=1)
        meeting.save()
        client.force_login(council_member)
        content = client.get(f"/leadership/meetings/{meeting.pk}/").content.decode()
        assert "Download calendar entry" not in content

    def test_upcoming_meeting_detail_shows_the_download_button(self, client, council_member, meeting):
        client.force_login(council_member)
        content = client.get(f"/leadership/meetings/{meeting.pk}/").content.decode()
        assert "Download calendar entry" in content


class TestCalendarFeed:
    """The token-gated subscribable feed of upcoming meetings (issue #186)."""

    FEED_URL = "/leadership/meetings/calendar.ics"

    def test_no_token_404s(self, client, meeting):
        assert client.get(self.FEED_URL).status_code == 404

    def test_wrong_token_404s(self, client, meeting):
        assert client.get(self.FEED_URL + "?token=nope").status_code == 404

    def test_valid_token_needs_no_login(self, client, meeting):
        response = client.get(self.FEED_URL + f"?token={CalendarFeed.current_token()}")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/calendar; charset=utf-8"
        body = response.content.decode()
        assert "BEGIN:VCALENDAR" in body
        assert f"UID:meeting-{meeting.pk}@blackpythondevs.org" in body

    def test_feed_holds_only_upcoming_meetings(self, client):
        upcoming = Meeting.objects.create(title="Next sync", scheduled_at=timezone.now() + timedelta(days=7))
        past = Meeting.objects.create(title="Old sync", scheduled_at=timezone.now() - timedelta(days=7))
        body = client.get(self.FEED_URL + f"?token={CalendarFeed.current_token()}").content.decode()
        assert f"UID:meeting-{upcoming.pk}@blackpythondevs.org" in body
        assert f"UID:meeting-{past.pk}@blackpythondevs.org" not in body
        assert body.count("BEGIN:VEVENT") == 1

    def test_token_is_stable(self, client):
        """Subscribers keep working: the token is generated once, not per request."""
        first = CalendarFeed.current_token()
        assert CalendarFeed.current_token() == first
        assert client.get(self.FEED_URL + f"?token={first}").status_code == 200


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
