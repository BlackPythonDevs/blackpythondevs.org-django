"""Sponsor-champion jobs console (issue #224).

A champion is a member in the "Corporate Sponsor" group with
`User.corporation_affiliate` set and the full Job permission set. They may
create/edit/delete only their own sponsor's jobs; every other sponsor's job
must 404, and no request-supplied sponsor id may widen that scope.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import Client
from django.utils import timezone

from core.models import CORPORATE_SPONSOR_GROUP_NAME
from corporate_sponsorships.models import Sponsor
from jobs.models import JOB_CHAMPION_PERMS, Job, can_champion_jobs

pytestmark = pytest.mark.django_db

MANAGE_LIST = "/jobs/manage/"
MANAGE_CREATE = "/jobs/manage/new/"


def _user(username, **extra):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pw",
        onboarding_completed_at=timezone.now(),
        **extra,
    )


@pytest.fixture
def own_sponsor(db):
    return Sponsor.objects.create(name="Own Corp", url="https://own.example.com")


@pytest.fixture
def other_sponsor(db):
    return Sponsor.objects.create(name="Other Corp", url="https://other.example.com")


@pytest.fixture
def champion(own_sponsor):
    user = _user("champion", corporation_affiliate=own_sponsor)
    user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
    return user


@pytest.fixture
def own_job(own_sponsor):
    return Job.objects.create(title="Own Job", apply_url="https://own.example.com/a", sponsor=own_sponsor)


@pytest.fixture
def other_job(other_sponsor):
    return Job.objects.create(title="Other Job", apply_url="https://other.example.com/a", sponsor=other_sponsor)


def _form_data(**extra):
    data = {
        "title": "New Role",
        "description": "",
        "apply_url": "https://own.example.com/apply",
        "location": "Accra",
        "employment_type": Job.EMPLOYMENT_FULL_TIME,
        "status": Job.STATUS_DRAFT,
    }
    data.update(extra)
    return data


class TestRoleHelper:
    def test_champion_passes(self, champion):
        assert can_champion_jobs(champion)

    def test_group_without_affiliation_fails(self, db):
        user = _user("noaffil")
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        assert not can_champion_jobs(user)

    def test_affiliation_without_group_fails(self, own_sponsor):
        assert not can_champion_jobs(_user("nogroup", corporation_affiliate=own_sponsor))

    def test_group_and_affiliation_without_perms_fails(self, own_sponsor):
        """Group + affiliation are not enough; the full permission set is required."""
        user = _user("noperms", corporation_affiliate=own_sponsor)
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        # Simulate the migration grant never having happened by deleting the perms.
        Permission.objects.filter(
            content_type__app_label="jobs", codename__in=[p.split(".")[1] for p in JOB_CHAMPION_PERMS]
        ).delete()
        assert not can_champion_jobs(user)

    def test_anonymous_fails(self):
        assert not can_champion_jobs(AnonymousUser())

    def test_superuser_without_affiliation_fails(self, db):
        admin = get_user_model().objects.create_superuser(username="root", email="root@example.com", password="pw")
        assert not can_champion_jobs(admin)


class TestConsoleAccess:
    def test_anonymous_redirected_to_login(self, client):
        response = client.get(MANAGE_LIST)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_ordinary_member_forbidden(self, client, db):
        client.force_login(_user("member"))
        assert client.get(MANAGE_LIST).status_code == 403

    def test_group_without_affiliation_gets_404(self, client, db):
        user = _user("noaffil")
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        client.force_login(user)
        assert client.get(MANAGE_LIST).status_code == 404

    def test_affiliation_without_group_gets_403(self, client, own_sponsor):
        # Without the group there are no Job perms, so PermissionRequiredMixin
        # denies before the role check runs. Either denial is acceptable.
        client.force_login(_user("nogroup", corporation_affiliate=own_sponsor))
        assert client.get(MANAGE_LIST).status_code in (403, 404)

    def test_champion_reaches_console(self, client, champion, own_job):
        client.force_login(champion)
        response = client.get(MANAGE_LIST)
        assert response.status_code == 200
        assert "Own Job" in response.content.decode()

    def test_create_form_renders(self, client, champion):
        client.force_login(champion)
        response = client.get(MANAGE_CREATE)
        assert response.status_code == 200
        assert "jobs/job_form.html" in [t.name for t in response.templates]

    def test_list_never_shows_another_sponsors_job(self, client, champion, own_job, other_job):
        client.force_login(champion)
        content = client.get(MANAGE_LIST).content.decode()
        assert "Own Job" in content
        assert "Other Job" not in content


class TestObjectScoping:
    def _routes(self, job):
        return [
            f"/jobs/manage/{job.pk}/",
            f"/jobs/manage/{job.pk}/edit/",
            f"/jobs/manage/{job.pk}/delete/",
        ]

    def test_other_sponsors_job_404s_on_every_route(self, client, champion, other_job):
        client.force_login(champion)
        for url in self._routes(other_job):
            assert client.get(url).status_code == 404, url

    def test_own_job_reachable_on_every_route(self, client, champion, own_job):
        client.force_login(champion)
        for url in self._routes(own_job):
            assert client.get(url).status_code == 200, url

    def test_editing_other_sponsors_job_posts_404_and_changes_nothing(self, client, champion, other_job):
        client.force_login(champion)
        response = client.post(f"/jobs/manage/{other_job.pk}/edit/", _form_data(title="Hijacked"))
        assert response.status_code == 404
        other_job.refresh_from_db()
        assert other_job.title == "Other Job"

    def test_deleting_other_sponsors_job_404s(self, client, champion, other_job):
        client.force_login(champion)
        response = client.post(f"/jobs/manage/{other_job.pk}/delete/")
        assert response.status_code == 404
        assert Job.objects.filter(pk=other_job.pk).exists()


class TestCreateScope:
    def test_champion_created_job_is_bound_to_own_sponsor(self, client, champion, own_sponsor):
        client.force_login(champion)
        response = client.post(MANAGE_CREATE, _form_data())
        assert response.status_code == 302
        job = Job.objects.get(title="New Role")
        assert job.sponsor_id == own_sponsor.pk

    def test_sponsor_id_in_post_cannot_widen_scope(self, client, champion, own_sponsor, other_sponsor):
        client.force_login(champion)
        response = client.post(MANAGE_CREATE, _form_data(sponsor=other_sponsor.pk, title="Sneaky"))
        assert response.status_code == 302
        job = Job.objects.get(title="Sneaky")
        assert job.sponsor_id == own_sponsor.pk

    def test_create_requires_csrf(self, champion, own_sponsor):
        # A client that actually enforces CSRF, unlike the default test client.
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(champion)
        response = csrf_client.post(MANAGE_CREATE, _form_data())
        assert response.status_code == 403
        assert not Job.objects.filter(title="New Role").exists()

    def test_publishing_stamps_published_at(self, client, champion):
        client.force_login(champion)
        client.post(
            MANAGE_CREATE,
            _form_data(status=Job.STATUS_PUBLISHED, is_published="on"),
        )
        job = Job.objects.get(title="New Role")
        assert job.published_at is not None


class TestChampionCannotReachOtherConsoles:
    def test_denied_corporate_and_event_consoles(self, client, champion, own_sponsor):
        client.force_login(champion)
        for url in ("/corporate-sponsors/", f"/corporate-sponsors/{own_sponsor.pk}/", "/event-sponsorships/"):
            assert client.get(url).status_code in (403, 404), url
        assert not champion.has_perm("corporate_sponsorships.change_sponsor")
