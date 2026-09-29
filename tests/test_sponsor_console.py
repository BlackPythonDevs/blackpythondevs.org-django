"""The corporate-sponsor console (core.views.SponsorView): a full-CRUD
neapolitan front-end that replaces the Wagtail snippet admin as the place to
manage `core.Sponsor` records.

Mirrors tests/test_sponsorships.py's access-control pattern. The embedded
checklist widget is covered separately in tests/test_checklists.py — this
file only checks that *this* console's own steps ("Corporate sponsor") show
up here and not the event-sponsorship ones.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from checklists.models import Task
from core.models import Sponsor

pytestmark = pytest.mark.django_db

CONSOLE_URLS = ["/sponsors/", "/sponsors/new/"]
DETAIL_URLS = ["/sponsors/{pk}/", "/sponsors/{pk}/edit/", "/sponsors/{pk}/delete/"]


@pytest.fixture
def sponsor(db):
    return Sponsor.objects.create(name="Acme Corp")


@pytest.fixture
def executor(db):
    user = get_user_model().objects.create_user(username="exec", email="exec@example.com", password="pw")
    user.groups.add(Group.objects.get(name="Executor"))
    return user


@pytest.fixture
def member(db):
    return get_user_model().objects.create_user(username="member", email="member@example.com", password="pw")


def all_urls(sponsor):
    return CONSOLE_URLS + [u.format(pk=sponsor.pk) for u in DETAIL_URLS]


class TestConsoleAccess:
    @pytest.mark.parametrize(
        "login_as,expected_status",
        [("executor", 200), (None, 302), ("member", 403)],
        ids=["executor", "anonymous", "ordinary_member"],
    )
    def test_console_access_by_role(self, request, client, sponsor, login_as, expected_status):
        if login_as:
            client.force_login(request.getfixturevalue(login_as))
        for url in all_urls(sponsor):
            assert client.get(url).status_code == expected_status, url


class TestConsoleTemplates:
    def test_site_templates_are_used(self, client, executor, sponsor):
        client.force_login(executor)
        expected = {
            "/sponsors/": "core/sponsor_list.html",
            "/sponsors/new/": "core/sponsor_form.html",
            f"/sponsors/{sponsor.pk}/": "core/sponsor_detail.html",
            f"/sponsors/{sponsor.pk}/edit/": "core/sponsor_form.html",
            f"/sponsors/{sponsor.pk}/delete/": "core/sponsor_confirm_delete.html",
        }
        for url, template in expected.items():
            names = [t.name for t in client.get(url).templates if t.name]
            assert template in names, f"{url} rendered {names}"


class TestConsoleWrites:
    def test_executor_can_create(self, client, executor):
        client.force_login(executor)
        response = client.post(
            "/sponsors/new/",
            {
                "name": "New Sponsor Co",
                "url": "",
                "logo_static_path": "",
                "sort_order": 0,
                "active": "on",
                "status": Sponsor.STATUS_ACTIVE,
                "invoice_paid_date": "",
                "contract_amount": "",
                "primary_contact_name": "",
                "primary_contact_email": "",
            },
        )
        assert response.status_code == 302
        assert Sponsor.objects.filter(name="New Sponsor Co").exists()

    def test_executor_can_delete(self, client, executor, sponsor):
        client.force_login(executor)
        response = client.post(f"/sponsors/{sponsor.pk}/delete/")
        assert response.status_code == 302
        assert not Sponsor.objects.filter(pk=sponsor.pk).exists()

    def test_anonymous_cannot_create(self, client):
        response = client.post("/sponsors/new/", {"name": "Should not exist"})
        assert response.status_code == 302
        assert not Sponsor.objects.filter(name="Should not exist").exists()


class TestMembersPageLink:
    """The "Leadership actions" panel on /members/ links to both consoles."""

    @pytest.fixture
    def onboarded_executor(self, executor):
        executor.onboarding_completed_at = timezone.now()
        executor.save()
        return executor

    @pytest.fixture
    def onboarded_member(self, member):
        member.onboarding_completed_at = timezone.now()
        member.save()
        return member

    def test_executor_sees_both_console_links(self, client, onboarded_executor):
        client.force_login(onboarded_executor)
        content = client.get("/members/").content.decode()
        assert "Corporate sponsors" in content
        assert 'href="/sponsors/"' in content
        assert "Event sponsorship requests" in content
        assert 'href="/sponsorships/"' in content

    def test_ordinary_member_does_not_see_the_links(self, client, onboarded_member):
        client.force_login(onboarded_member)
        content = client.get("/members/").content.decode()
        assert "Corporate sponsors" not in content
        assert "Event sponsorship requests" not in content


class TestChecklistWidgetIsTheCorporateOne:
    """Confirm the embedded widget shows Sponsor's own steps, not
    SponsorshipRequest's — each model's checklist is independent (separate
    content_type/object_id rows), but this pins the visible behavior."""

    def test_checklist_page_shows_corporate_sponsor_steps(self, client, executor, sponsor):
        client.force_login(executor)
        response = client.get(f"/checklists/core/sponsor/{sponsor.pk}/")
        content = response.content.decode()
        assert "Corporate sponsor checklist" in content
        assert "Contract sent" in content
        assert "Prospectus reviewed" not in content

    def test_detail_page_links_to_the_checklist_instead_of_embedding_it(self, client, executor, sponsor):
        client.force_login(executor)
        content = client.get(f"/sponsors/{sponsor.pk}/").content.decode()
        assert f'href="/checklists/core/sponsor/{sponsor.pk}/"' in content
        assert "Contract sent" not in content


class TestTaskActivityOnTheChecklistPage:
    """django-auditlog already tracks every model; {% task_activity %} on the
    checklist page itself (not the checklist widget — see checklists_tags.py)
    surfaces Task's own history inline rather than sending Executors to the
    superuser-only django-admin audit log (core/admin_auditlog.py)."""

    def test_toggling_a_task_shows_up_as_activity_on_the_checklist_page(self, client, executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        client.post(f"/checklists/core/sponsor/{sponsor.pk}/", {"action": "toggle", "task_id": task.pk})

        response = client.get(f"/checklists/core/sponsor/{sponsor.pk}/")
        content = response.content.decode()
        assert "Task activity" in content
        assert task.title in content
        assert executor.username in content
        assert "is done" in content
