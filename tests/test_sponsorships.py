"""The two sponsorship surfaces: the Executor console and the public intake form.

The neapolitan CRUDView at /event-sponsorships/ is a management console — it demands
the full add/change/delete/view set, so ordinary members and anonymous visitors
are bounced. The form at /event-sponsorships/request/ is the opposite: open to anyone,
since the organisers who need it come from outside the community.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from event_sponsorships.models import SponsorshipRequest

pytestmark = pytest.mark.django_db

CONSOLE_URLS = ["/event-sponsorships/", "/event-sponsorships/new/"]
DETAIL_URLS = ["/event-sponsorships/{pk}/", "/event-sponsorships/{pk}/edit/", "/event-sponsorships/{pk}/delete/"]


@pytest.fixture
def sponsorship(db):
    return SponsorshipRequest.objects.create(
        name="PyCon Somewhere",
        start_date=datetime.date(2026, 5, 1),
        country="NG",
    )


@pytest.fixture
def executor(db):
    user = get_user_model().objects.create_user(username="exec", email="exec@example.com", password="pw")
    user.groups.add(Group.objects.get(name="Executor"))
    return user


@pytest.fixture
def member(db):
    return get_user_model().objects.create_user(username="member", email="member@example.com", password="pw")


def all_urls(sponsorship):
    return CONSOLE_URLS + [u.format(pk=sponsorship.pk) for u in DETAIL_URLS]


class TestConsoleAccess:
    """PermissionRequiredMixin's own split: bounces anonymous, 403s unprivileged, 200s executor."""

    @pytest.mark.parametrize(
        "login_as,expected_status",
        [("executor", 200), (None, 302), ("member", 403)],
        ids=["executor", "anonymous", "ordinary_member"],
    )
    def test_console_access_by_role(self, request, client, sponsorship, login_as, expected_status):
        if login_as:
            client.force_login(request.getfixturevalue(login_as))
        for url in all_urls(sponsorship):
            assert client.get(url).status_code == expected_status, url


class TestConsoleTemplates:
    """The site's own templates must win over neapolitan's Tailwind defaults."""

    def test_site_templates_are_used(self, client, executor, sponsorship):
        client.force_login(executor)
        expected = {
            "/event-sponsorships/": "event_sponsorships/sponsorshiprequest_list.html",
            "/event-sponsorships/new/": "event_sponsorships/sponsorshiprequest_form.html",
            f"/event-sponsorships/{sponsorship.pk}/": "event_sponsorships/sponsorshiprequest_detail.html",
            f"/event-sponsorships/{sponsorship.pk}/edit/": "event_sponsorships/sponsorshiprequest_form.html",
            f"/event-sponsorships/{sponsorship.pk}/delete/": (
                "event_sponsorships/sponsorshiprequest_confirm_delete.html"
            ),
        }
        for url, template in expected.items():
            names = [t.name for t in client.get(url).templates if t.name]
            assert template in names, f"{url} rendered {names}"

    def test_list_does_not_leak_template_comment(self, client, executor):
        """A multi-line `{# #}` comment only closes at the first newline, so its
        second line leaked as visible text on the paginated list (issue #220).
        Pagination must render before the block is reached, and no comment
        fragment may appear in the body."""
        for i in range(26):
            SponsorshipRequest.objects.create(
                name=f"Event {i}",
                start_date=datetime.date(2026, 5, 1),
                country="NG",
            )
        client.force_login(executor)
        body = client.get("/event-sponsorships/").content.decode()
        assert "Page 1 of 2" in body  # the pagination section rendered
        assert "active filters survive paging" not in body
        assert "Django reads the last" not in body

    def test_detail_shows_staff_only_fields(self, client, executor, sponsorship):
        sponsorship.notes = "Chased the organiser twice."
        sponsorship.save()
        client.force_login(executor)
        body = client.get(f"/event-sponsorships/{sponsorship.pk}/").content.decode()
        assert "Chased the organiser twice." in body
        assert "Internal notes" in body


class TestConsoleWrites:
    def test_executor_can_create_and_derived_fields_are_set(self, client, executor):
        client.force_login(executor)
        response = client.post(
            "/event-sponsorships/new/",
            {
                "name": "DjangoCon Lagos",
                "url": "https://example.com",
                "prospectus_url": "",
                "start_date": "2027-09-14",
                "country": "NG",
                "amount_requested": "2500.00",
                "notes": "",
            },
        )
        assert response.status_code == 302, response.context["form"].errors if response.context else ""
        created = SponsorshipRequest.objects.get(name="DjangoCon Lagos")
        assert created.year == 2027
        assert created.region  # derived from country
        assert created.amount_requested == Decimal("2500.00")
        assert created.status == SponsorshipRequest.REQUESTED

    def test_executor_can_delete(self, client, executor, sponsorship):
        client.force_login(executor)
        assert client.post(f"/event-sponsorships/{sponsorship.pk}/delete/").status_code == 302
        assert not SponsorshipRequest.objects.filter(pk=sponsorship.pk).exists()

    def test_anonymous_cannot_create(self, client):
        client.post(
            "/event-sponsorships/new/",
            {"name": "Sneaky", "start_date": "2027-01-01", "country": "US"},
        )
        assert not SponsorshipRequest.objects.filter(name="Sneaky").exists()


class TestPublicIntake:
    def test_anonymous_can_open_the_form(self, client):
        response = client.get("/event-sponsorships/request/")
        assert response.status_code == 200
        assert "event_sponsorships/request_form.html" in [t.name for t in response.templates if t.name]

    def test_internal_notes_are_not_exposed(self, client):
        form = client.get("/event-sponsorships/request/").context["form"]
        assert "notes" not in form.fields
        assert "status" not in form.fields
        assert "paid" not in form.fields

    def test_submission_creates_a_requested_record(self, client):
        response = client.post(
            "/event-sponsorships/request/",
            {
                "name": "PyCon Nairobi",
                "url": "https://example.org",
                "prospectus_url": "",
                "start_date": "2027-03-02",
                "country": "KE",
                "amount_requested": "1000",
            },
        )
        assert response.status_code == 302
        created = SponsorshipRequest.objects.get(name="PyCon Nairobi")
        assert created.status == SponsorshipRequest.REQUESTED
        assert created.year == 2027
        assert created.notes == ""
        assert not created.is_published

    def test_member_organiser_links_to_their_account(self, client, member):
        """A request filed with a member's email links to that account, so
        the organiser can get reminders and updates once approved (issue
        #144)."""
        response = client.post(
            "/event-sponsorships/request/",
            {
                "name": "PyCon Nairobi",
                "url": "https://example.org",
                "prospectus_url": "",
                "start_date": "2027-03-02",
                "country": "KE",
                "amount_requested": "1000",
                "contact_name": "Mem Ber",
                "contact_email": "Member@Example.com",
            },
        )
        assert response.status_code == 302
        created = SponsorshipRequest.objects.get(name="PyCon Nairobi")
        assert created.contact_user == member

    def test_unknown_contact_email_stays_unlinked(self, client):
        """No account yet — the record keeps the bare email until one exists."""
        client.post(
            "/event-sponsorships/request/",
            {
                "name": "PyCon Nairobi",
                "url": "",
                "prospectus_url": "",
                "start_date": "2027-03-02",
                "country": "KE",
                "amount_requested": "",
                "contact_name": "Out Sider",
                "contact_email": "outsider@example.com",
            },
        )
        created = SponsorshipRequest.objects.get(name="PyCon Nairobi")
        assert created.contact_email == "outsider@example.com"
        assert created.contact_user is None

    def test_thanks_page_renders(self, client):
        assert client.get("/event-sponsorships/request/thanks/").status_code == 200

    def test_intake_url_is_not_swallowed_by_the_detail_route(self, client):
        """`request/` must not be read as a CRUD pk lookup."""
        response = client.get("/event-sponsorships/request/")
        assert response.resolver_match.url_name == "event-sponsorship-request"


class TestStatusChange:
    """The console's status control: POST-only, validated, and audited.

    STATUS_CHOICES is the gate on `is_published`, so the endpoint must reject
    anything outside it rather than assigning the raw input to the field.
    """

    def status_url(self, sponsorship):
        return f"/event-sponsorships/{sponsorship.pk}/status/"

    def test_executor_can_change_status(self, client, executor, sponsorship):
        client.force_login(executor)
        response = client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.COMPLETED})
        assert response.status_code == 302
        sponsorship.refresh_from_db()
        assert sponsorship.status == SponsorshipRequest.COMPLETED

    def test_get_is_rejected(self, client, executor, sponsorship):
        """A state change must never be reachable by GET."""
        client.force_login(executor)
        assert client.get(self.status_url(sponsorship)).status_code == 405
        sponsorship.refresh_from_db()
        assert sponsorship.status == SponsorshipRequest.REQUESTED

    @pytest.mark.parametrize("login_as,expected_status", [("member", 403), (None, 302)], ids=["member", "anonymous"])
    def test_non_executor_is_denied(self, request, client, sponsorship, login_as, expected_status):
        if login_as:
            client.force_login(request.getfixturevalue(login_as))
        response = client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        assert response.status_code == expected_status
        sponsorship.refresh_from_db()
        assert sponsorship.status == SponsorshipRequest.REQUESTED

    def test_invalid_status_is_rejected(self, client, executor, sponsorship):
        client.force_login(executor)
        response = client.post(self.status_url(sponsorship), {"status": "published"})
        assert response.status_code == 302
        sponsorship.refresh_from_db()
        assert sponsorship.status == SponsorshipRequest.REQUESTED
        assert not sponsorship.is_published

    def test_status_change_is_audited(self, client, executor, sponsorship):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        client.force_login(executor)
        LogEntry.objects.all().delete()
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})

        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        entry = LogEntry.objects.get(content_type=content_type, object_id=sponsorship.pk)
        assert entry.actor == executor
        assert entry.changes["status"] == [SponsorshipRequest.REQUESTED, SponsorshipRequest.APPROVED]

    def test_status_change_leaves_notes_and_amount_untouched(self, client, executor, sponsorship):
        sponsorship.notes = "Keep this private."
        sponsorship.amount_requested = Decimal("1234.00")
        sponsorship.save()
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        sponsorship.refresh_from_db()
        assert sponsorship.notes == "Keep this private."
        assert sponsorship.amount_requested == Decimal("1234.00")

    def test_detail_page_offers_the_control_to_executors(self, client, executor, sponsorship):
        client.force_login(executor)
        body = client.get(f"/event-sponsorships/{sponsorship.pk}/").content.decode()
        assert self.status_url(sponsorship) in body
        assert 'name="status"' in body

    def task(self, sponsorship, title):
        from django.contrib.contenttypes.models import ContentType

        from checklists.models import Task

        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        return Task.objects.get(content_type=content_type, object_id=sponsorship.pk, title=title)

    def test_approving_ticks_the_default_approved_task(self, client, executor, sponsorship):
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        task = self.task(sponsorship, "Approved")
        assert task.is_done is True
        assert task.done_by == executor
        assert task.done_at is not None

    def test_completing_ticks_the_default_event_completed_task(self, client, executor, sponsorship):
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.COMPLETED})
        task = self.task(sponsorship, "Event completed")
        assert task.is_done is True
        assert task.done_by == executor
        assert task.done_at is not None

    def test_completing_clears_the_approved_task(self, client, executor, sponsorship):
        """Leaving `approved` clears the task `approved` owned, even though
        the move is to `completed` rather than back to `requested`."""
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.COMPLETED})
        approved = self.task(sponsorship, "Approved")
        assert approved.is_done is False
        assert approved.done_by is None
        assert approved.done_at is None

    def test_reverting_to_requested_clears_the_tasks(self, client, executor, sponsorship):
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.COMPLETED})
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.REQUESTED})
        for title in ("Approved", "Event completed"):
            task = self.task(sponsorship, title)
            assert task.is_done is False
            assert task.done_by is None
            assert task.done_at is None

    def test_status_change_leaves_other_default_tasks_alone(self, client, executor, sponsorship):
        """Only the mapped titles are managed; a manually ticked step keeps
        its state through a status change."""
        from django.contrib.contenttypes.models import ContentType

        from checklists.models import Task

        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        Task.objects.filter(content_type=content_type, object_id=sponsorship.pk, title="Prospectus reviewed").update(
            is_done=True
        )
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        assert self.task(sponsorship, "Prospectus reviewed").is_done is True
        assert self.task(sponsorship, "Approved").is_done is True
        assert self.task(sponsorship, "Funds transferred").is_done is False

    def test_adhoc_tasks_are_left_alone(self, client, executor, sponsorship):
        from django.contrib.contenttypes.models import ContentType

        from checklists.models import Task

        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        adhoc = Task.objects.create(
            content_type=content_type, object_id=sponsorship.pk, title="Approved", is_default=False
        )
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        adhoc.refresh_from_db()
        assert adhoc.is_done is False

    def test_other_requests_default_tasks_are_left_alone(self, client, executor, sponsorship):
        other = SponsorshipRequest.objects.create(
            name="Other Event", start_date=datetime.date(2026, 6, 1), country="KE"
        )
        client.force_login(executor)
        client.post(self.status_url(sponsorship), {"status": SponsorshipRequest.APPROVED})
        assert self.task(other, "Approved").is_done is False

    def test_member_cannot_publish_by_ticking_the_event_completed_task(self, client, member, sponsorship):
        """Ticking a checklist task must never write status; only the
        permission-gated status endpoint can publish."""
        task = self.task(sponsorship, "Event completed")
        client.force_login(member)
        response = client.post(
            f"/checklists/event_sponsorships/sponsorshiprequest/{sponsorship.pk}/",
            {"action": "toggle", "task_id": task.pk},
        )
        assert response.status_code == 403
        sponsorship.refresh_from_db()
        assert sponsorship.status == SponsorshipRequest.REQUESTED
        assert not sponsorship.is_published
        task.refresh_from_db()
        assert task.is_done is False

    def test_executor_ticking_a_task_does_not_publish(self, client, executor, sponsorship):
        """Even with checklist rights, ticking alone never flips status."""
        task = self.task(sponsorship, "Event completed")
        client.force_login(executor)
        client.post(
            f"/checklists/event_sponsorships/sponsorshiprequest/{sponsorship.pk}/",
            {"action": "toggle", "task_id": task.pk},
        )
        sponsorship.refresh_from_db()
        assert sponsorship.status == SponsorshipRequest.REQUESTED
        assert not sponsorship.is_published
