"""CoC reports: public intake, confidentiality, and the no-delete rule.

The guarantees under test (see coc_reports.models and the issue's security
conditions):

- Anyone can file a report, but the submitting user is captured even when
  they file anonymously — for notification only, never rendered back.
- Filing leaves no audit trail naming the reporter (the model is excluded
  from django-auditlog, like elections.Ballot).
- Filing seeds the four-step CoC checklist via the generic checklists app.
- The checklists console — open to the Executor group's checklists
  permissions — hides CoC reports entirely from anyone without the COC
  Report Viewing role, and renders no report text even to those who have it.
- A report's only status transition is under review → closed, enforced
  server-side; closing notifies the captured reporter.
- A report cannot be un-created: no delete permission, no delete action,
  no delete view — not even for superusers.
"""

import datetime

import pytest
from auditlog.models import LogEntry
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from checklists.models import Task
from coc_reports.admin import CocReportAdmin
from coc_reports.models import CocReport
from notifications.models import UserNotification

pytestmark = pytest.mark.django_db

CHECKLIST_STEPS = [
    "CoC has made initial confirmation of response",
    "CoC has discussed",
    "Conclusion has been found",
    "Reporter has been notified",
]


def make_user(username, **kwargs):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="pw", **kwargs
    )


@pytest.fixture
def reporter(db):
    return make_user("reporter")


@pytest.fixture
def coc_viewer(db):
    """A COC Report Viewing role holder who also works the checklists
    console (the role's group carries no checklists.* permissions, and the
    generic console requires those on top of any per-model ones)."""
    user = make_user("cocviewer")
    user.groups.add(Group.objects.get(name="COC Report Viewing"))
    user.groups.add(Group.objects.get(name="Executor"))
    return user


@pytest.fixture
def executor(db):
    """A checklist-console user (Executor group) with no CoC role."""
    user = make_user("exec")
    user.groups.add(Group.objects.get(name="Executor"))
    return user


def file_report(client, user=None, **form_kwargs):
    if user:
        client.force_login(user)
    data = {"description": "Something inappropriate happened at the meetup.", **form_kwargs}
    return client.post(reverse("coc-report"), data)


class TestIntake:
    def test_form_is_open_to_anonymous_visitors(self, client):
        response = client.get(reverse("coc-report"))
        assert response.status_code == 200
        assert b"Code of Conduct Violation" in response.content

    def test_filing_creates_an_under_review_report(self, client, reporter):
        response = file_report(client, reporter)
        assert response.status_code == 302

        report = CocReport.objects.get()
        assert report.description == "Something inappropriate happened at the meetup."
        assert report.status == CocReport.UNDER_REVIEW
        assert report.date_reported == datetime.date.today()
        assert report.reporter == reporter
        assert not report.is_anonymous

    def test_anonymous_filing_still_captures_the_user(self, client, reporter):
        response = file_report(client, reporter, is_anonymous="on")
        assert response.status_code == 302

        report = CocReport.objects.get()
        assert report.is_anonymous
        # Anonymous does not mean unreachable: the user is captured so the
        # CoC team can notify them of the outcome.
        assert report.reporter == reporter

    def test_logged_out_filing_has_no_reporter(self, client):
        response = file_report(client)
        assert response.status_code == 302
        assert CocReport.objects.get().reporter is None

    def test_filing_seeds_the_four_step_checklist(self, client, reporter):
        file_report(client, reporter)
        report = CocReport.objects.get()
        tasks = list(Task.objects.filter(object_id=report.pk))
        assert [task.title for task in tasks] == CHECKLIST_STEPS

    def test_filing_leaves_no_audit_trail_of_the_reporter(self, client, reporter):
        client.force_login(reporter)
        LogEntry.objects.all().delete()
        file_report(client, reporter)
        content_type = ContentType.objects.get_for_model(CocReport)
        assert not LogEntry.objects.filter(content_type=content_type).exists()


class TestConfidentiality:
    def test_str_reveals_nothing(self, reporter):
        report = CocReport.objects.create(description="secret words in here", reporter=reporter)
        assert "secret" not in str(report)
        assert str(report) == f"CoC report #{report.pk} (Under review)"

    def test_checklists_console_hides_reports_without_the_role(self, client, executor, reporter):
        report = CocReport.objects.create(description="confidential text", reporter=reporter)
        client.force_login(executor)

        assert client.get(reverse("checklists-object-list", args=["coc_reports", "cocreport"])).status_code == 403
        assert client.get(reverse("checklists-detail", args=["coc_reports", "cocreport", report.pk])).status_code == 403

    def test_checklists_index_hides_reports_without_the_role(self, client, executor):
        client.force_login(executor)
        response = client.get(reverse("checklists-index"))
        assert "Code of Conduct report" not in response.content.decode()

    def test_checklists_index_lists_reports_for_the_role(self, client, coc_viewer):
        client.force_login(coc_viewer)
        response = client.get(reverse("checklists-index"))
        assert "Code of Conduct report" in response.content.decode()

    def test_checklists_console_renders_no_report_text_for_the_role(self, client, coc_viewer, reporter):
        report = CocReport.objects.create(description="confidential text", reporter=reporter)
        client.force_login(coc_viewer)
        response = client.get(reverse("checklists-detail", args=["coc_reports", "cocreport", report.pk]))
        assert response.status_code == 200
        assert "confidential text" not in response.content.decode()

    def test_report_detail_never_shows_the_reporter(self, client, coc_viewer, reporter):
        report = CocReport.objects.create(description="A report.", reporter=reporter)
        client.force_login(coc_viewer)
        response = client.get(reverse("coc-report-detail", args=[report.pk]))
        assert response.status_code == 200
        assert reporter.email not in response.content.decode()
        assert "reporter" not in response.context


class TestStatusTransitions:
    def test_viewer_can_close_a_report_and_reporter_is_notified(self, client, coc_viewer, reporter):
        report = CocReport.objects.create(description="A report.", reporter=reporter)
        client.force_login(coc_viewer)
        response = client.post(reverse("coc-report-detail", args=[report.pk]), {"status": CocReport.CLOSED})
        assert response.status_code == 302

        report.refresh_from_db()
        assert report.status == CocReport.CLOSED
        assert UserNotification.objects.filter(recipient=reporter).count() == 1

    def test_closed_report_cannot_be_reopened(self, client, coc_viewer, reporter):
        report = CocReport.objects.create(description="A report.", reporter=reporter, status=CocReport.CLOSED)
        client.force_login(coc_viewer)
        client.post(reverse("coc-report-detail", args=[report.pk]), {"status": CocReport.UNDER_REVIEW})

        report.refresh_from_db()
        assert report.status == CocReport.CLOSED

    def test_closing_needs_change_permission(self, client, reporter):
        """A view-only COC viewer (or anyone else) can't close a report."""
        viewer = make_user("viewonly")
        viewer.groups.add(Group.objects.get(name="COC Report Viewing"))
        # Strip the group's change permission, leaving view only.
        group = Group.objects.get(name="COC Report Viewing")
        group.permissions.remove(
            Permission.objects.get(codename="change_cocreport", content_type__app_label="coc_reports")
        )

        report = CocReport.objects.create(description="A report.", reporter=reporter)
        client.force_login(viewer)
        response = client.post(reverse("coc-report-detail", args=[report.pk]), {"status": CocReport.CLOSED})
        assert response.status_code == 403
        report.refresh_from_db()
        assert report.status == CocReport.UNDER_REVIEW


class TestCannotBeUnCreated:
    def test_admin_has_no_delete_permission_or_action(self, reporter, rf):
        report = CocReport.objects.create(description="A report.", reporter=reporter)
        model_admin = CocReportAdmin(CocReport, admin.site)
        request = rf.get("/")

        assert not model_admin.has_delete_permission(request, report)
        assert not model_admin.has_add_permission(request)
        assert "delete_selected" not in model_admin.get_actions(request)

    def test_admin_delete_view_is_forbidden_even_for_superusers(self, client, reporter):
        root = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="pw", onboarding_completed_at=timezone.now()
        )
        report = CocReport.objects.create(description="A report.", reporter=reporter)
        client.force_login(root)

        response = client.post(f"/django-admin/coc_reports/cocreport/{report.pk}/delete/", {"post": "yes"})
        assert response.status_code == 403
        assert CocReport.objects.filter(pk=report.pk).exists()

    def test_there_is_no_delete_url_on_the_console(self, client, coc_viewer, reporter):
        report = CocReport.objects.create(description="A report.", reporter=reporter)
        client.force_login(coc_viewer)
        response = client.post(reverse("coc-report-detail", args=[report.pk]), {"action": "delete"})
        assert response.status_code in (302, 400)
        assert CocReport.objects.filter(pk=report.pk).exists()


class TestAccess:
    def test_console_is_closed_to_anonymous_visitors(self, client):
        response = client.get(reverse("coc-report-list"))
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_console_is_closed_to_plain_members(self, client):
        member = make_user("member")
        client.force_login(member)
        assert client.get(reverse("coc-report-list")).status_code == 403

    def test_viewer_can_list_and_read(self, client, coc_viewer, reporter):
        report = CocReport.objects.create(description="A report.", reporter=reporter)
        client.force_login(coc_viewer)
        assert client.get(reverse("coc-report-list")).status_code == 200
        assert client.get(reverse("coc-report-detail", args=[report.pk])).status_code == 200
