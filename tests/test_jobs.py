"""Jobs app: Job model storage, URL validation, admin, and #222 allowlists."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from corporate_sponsorships.models import Sponsor
from jobs.admin import JobAdmin
from jobs.models import Job, can_champion_jobs

pytestmark = pytest.mark.django_db


def _bad_url(value):
    field = Job._meta.get_field("apply_url")
    validator = field.validators[0]
    with pytest.raises(ValidationError):
        validator(value)


def test_dangerous_apply_url_schemes_are_rejected():
    """javascript:/data: and protocol-relative URLs must fail validation (#223)."""
    for value in (
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "//evil.example.com/apply",
    ):
        _bad_url(value)


def test_valid_apply_url_passes():
    field = Job._meta.get_field("apply_url")
    field.validators[0]("https://careers.example.com/apply")


def test_apply_url_is_a_url_field():
    """The model field is a URLField, not a CharField, so the validator runs."""
    from django.db import models

    assert isinstance(Job._meta.get_field("apply_url"), models.URLField)


@pytest.fixture
def sponsor(db):
    return Sponsor.objects.create(name="Jobs Corp", url="https://jobs.example.com")


def test_defaults(sponsor):
    job = Job.objects.create(title="Backend Engineer", apply_url="https://jobs.example.com/a", sponsor=sponsor)
    assert job.remote is False
    assert job.employment_type == Job.EMPLOYMENT_FULL_TIME
    assert job.status == Job.STATUS_DRAFT
    assert job.is_published is False
    assert job.created_at is not None
    assert job.updated_at is not None


def test_str(sponsor):
    job = Job.objects.create(title="Backend Engineer", apply_url="https://jobs.example.com/a", sponsor=sponsor)
    assert str(job) == "Backend Engineer"


def test_sponsor_fk_cascade(sponsor):
    Job.objects.create(title="Role", apply_url="https://jobs.example.com/a", sponsor=sponsor)
    sponsor.delete()
    assert Job.objects.count() == 0


def test_source_external_id_unique_when_both_set(sponsor):
    Job.objects.create(
        title="Role", apply_url="https://jobs.example.com/a", sponsor=sponsor, source="feed", external_id="42"
    )
    with pytest.raises(IntegrityError):
        Job.objects.create(
            title="Role 2", apply_url="https://jobs.example.com/b", sponsor=sponsor, source="feed", external_id="42"
        )


def test_blank_source_external_id_not_unique(sponsor):
    """Rows with no provenance must not collide on the partial unique constraint."""
    Job.objects.create(title="A", apply_url="https://jobs.example.com/a", sponsor=sponsor)
    Job.objects.create(title="B", apply_url="https://jobs.example.com/b", sponsor=sponsor)
    assert Job.objects.count() == 2


def test_admin_registered():
    assert admin.site.is_registered(Job)
    assert isinstance(admin.site._registry[Job], JobAdmin)


def test_public_and_internal_allowlists_are_explicit_and_disjoint():
    assert isinstance(Job.PUBLIC_FIELDS, tuple)
    assert isinstance(Job.INTERNAL_FIELDS, tuple)
    # Non-public bookkeeping must never be in the public allowlist.
    for internal in ("status", "is_published", "source", "external_id", "created_at", "updated_at"):
        assert internal in Job.INTERNAL_FIELDS
        assert internal not in Job.PUBLIC_FIELDS


def test_get_public_data_only_returns_public_fields(sponsor):
    job = Job.objects.create(
        title="Role",
        apply_url="https://jobs.example.com/a",
        sponsor=sponsor,
        status=Job.STATUS_EXPIRED,
        source="feed",
        external_id="7",
    )
    data = job.get_public_data()
    assert set(data) == set(Job.PUBLIC_FIELDS)
    assert "status" not in data
    assert "source" not in data
    assert "external_id" not in data


def test_admin_search_fields_exclude_internal_only_fields():
    # search_fields must not invite searching internal ingest bookkeeping.
    assert "source" not in JobAdmin.search_fields
    assert "external_id" not in JobAdmin.search_fields


def _publish(job):
    job.status = Job.STATUS_PUBLISHED
    job.is_published = True
    job.published_at = timezone.now()
    job.save()
    return job


class TestPublicJobPages:
    """Issue #224: /jobs/ and /jobs/<pk>/ render published jobs only."""

    def test_list_shows_published_job(self, client, sponsor):
        job = _publish(
            Job.objects.create(
                title="Backend Engineer",
                apply_url="https://jobs.example.com/a",
                sponsor=sponsor,
            )
        )
        response = client.get(reverse("jobs-public-list"))
        assert response.status_code == 200
        assert "Backend Engineer" in response.content.decode()
        assert job.title in response.content.decode()

    @pytest.mark.parametrize("status", [Job.STATUS_DRAFT, Job.STATUS_EXPIRED])
    def test_non_published_status_never_lists_or_details(self, client, sponsor, status):
        job = Job.objects.create(
            title="Hidden Role",
            apply_url="https://jobs.example.com/a",
            sponsor=sponsor,
            status=status,
            is_published=True,
        )
        assert "Hidden Role" not in client.get(reverse("jobs-public-list")).content.decode()
        assert client.get(reverse("jobs-public-detail", args=[job.pk])).status_code == 404

    def test_unpublished_flag_hides_published_status_job(self, client, sponsor):
        job = Job.objects.create(
            title="Flagged Off Role",
            apply_url="https://jobs.example.com/a",
            sponsor=sponsor,
            status=Job.STATUS_PUBLISHED,
            is_published=False,
        )
        assert "Flagged Off Role" not in client.get(reverse("jobs-public-list")).content.decode()
        assert client.get(reverse("jobs-public-detail", args=[job.pk])).status_code == 404

    def test_detail_404_for_unknown_id(self, client, db):
        assert client.get(reverse("jobs-public-detail", args=[999999])).status_code == 404

    def test_published_detail_shows_only_public_fields(self, client, sponsor):
        sponsor.contract_amount = 987654
        sponsor.primary_contact_name = "Secret Contact"
        sponsor.primary_contact_email = "secret@example.com"
        sponsor.save()
        job = _publish(
            Job.objects.create(
                title="Backend Engineer",
                description="Build things.",
                apply_url="https://jobs.example.com/a",
                location="Accra",
                sponsor=sponsor,
                source="feed",
                external_id="42",
            )
        )
        content = client.get(reverse("jobs-public-detail", args=[job.pk])).content.decode()
        assert "Backend Engineer" in content
        for hidden in ("987654", "Secret Contact", "secret@example.com", "feed", "42"):
            assert hidden not in content, hidden

    def test_public_routes_reject_post(self, client, sponsor):
        job = _publish(Job.objects.create(title="Role", apply_url="https://jobs.example.com/a", sponsor=sponsor))
        assert client.post(reverse("jobs-public-list")).status_code == 405
        assert client.post(reverse("jobs-public-detail", args=[job.pk])).status_code == 405


class TestSponsorJobCreate:
    """Issue #231: a corporate-sponsorship manager adds one job from a
    sponsor's console page, without needing the champion role.

    The route reuses JobForm, so the sponsor comes from the URL only (never
    from the POST) and the full corporate-sponsor permission set is required,
    exactly as on SponsorView itself.
    """

    def _create_url(self, sponsor):
        return reverse("corporate-sponsors-job-create", args=[sponsor.pk])

    @pytest.fixture
    def other_sponsor(self, db):
        return Sponsor.objects.create(name="Other Corp", url="https://other.example.com")

    @pytest.fixture
    def manager(self, db):
        """Holds the four Sponsor perms directly, like the console's own
        executor fixture; no Job perms and no champion role."""
        user = get_user_model().objects.create_user(
            username="corp", email="corp@example.com", password="pw", onboarding_completed_at=timezone.now()
        )
        perms = [
            Permission.objects.get(content_type__app_label="corporate_sponsorships", codename=f"{action}_sponsor")
            for action in ("view", "add", "change", "delete")
        ]
        user.user_permissions.add(*perms)
        return user

    @pytest.fixture
    def member(self, db):
        return get_user_model().objects.create_user(
            username="member", email="member@example.com", password="pw", onboarding_completed_at=timezone.now()
        )

    @staticmethod
    def _form_data(**extra):
        data = {
            "title": "One-off Role",
            "description": "A one-time posting.",
            "apply_url": "https://jobs.example.com/apply",
            "location": "Accra",
            "employment_type": Job.EMPLOYMENT_FULL_TIME,
            "status": Job.STATUS_DRAFT,
        }
        data.update(extra)
        return data

    def test_anonymous_is_redirected_to_login(self, client, sponsor):
        response = client.get(self._create_url(sponsor))
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_unrelated_member_is_forbidden(self, client, member, sponsor):
        client.force_login(member)
        assert client.get(self._create_url(sponsor)).status_code == 403
        assert client.post(self._create_url(sponsor), self._form_data()).status_code == 403
        assert not Job.objects.filter(title="One-off Role").exists()

    def test_manager_gets_the_form(self, client, manager, sponsor):
        client.force_login(manager)
        response = client.get(self._create_url(sponsor))
        assert response.status_code == 200
        assert "jobs/sponsor_job_form.html" in [t.name for t in response.templates]
        assert sponsor.name in response.content.decode()

    def test_manager_creates_job_bound_to_url_sponsor(self, client, manager, sponsor):
        client.force_login(manager)
        response = client.post(self._create_url(sponsor), self._form_data())
        assert response.status_code == 302
        assert response["Location"] == reverse("corporate-sponsors-detail", args=[sponsor.pk])
        job = Job.objects.get(title="One-off Role")
        assert job.sponsor_id == sponsor.pk

    def test_sponsor_id_in_post_cannot_retarget_the_job(self, client, manager, sponsor, other_sponsor):
        """A `sponsor` id in the body must not bind the job to another company."""
        client.force_login(manager)
        response = client.post(self._create_url(sponsor), self._form_data(sponsor=other_sponsor.pk, title="Sneaky"))
        assert response.status_code == 302
        job = Job.objects.get(title="Sneaky")
        assert job.sponsor_id == sponsor.pk

    def test_creating_for_another_sponsor_uses_that_sponsors_page(self, client, manager, sponsor, other_sponsor):
        """The URL sponsor wins; the manager may target whichever sponsor page
        they are authorised to open, and it is the URL that decides."""
        client.force_login(manager)
        client.post(self._create_url(other_sponsor), self._form_data(title="Other Role"))
        job = Job.objects.get(title="Other Role")
        assert job.sponsor_id == other_sponsor.pk

    def test_publishing_stamps_published_at(self, client, manager, sponsor):
        client.force_login(manager)
        client.post(self._create_url(sponsor), self._form_data(status=Job.STATUS_PUBLISHED, is_published="on"))
        job = Job.objects.get(title="One-off Role")
        assert job.published_at is not None

    def test_manager_does_not_need_job_perms_or_champion_role(self, client, manager):
        assert not manager.has_perm("jobs.add_job")
        assert not can_champion_jobs(manager)

    def test_sponsor_affiliated_champion_without_console_perms_is_forbidden(self, client, sponsor):
        """A champion (own sponsor, Job perms) is not a corporate-sponsorship
        manager and must not reach this console path for any sponsor."""
        from django.contrib.auth.models import Group

        from core.models import CORPORATE_SPONSOR_GROUP_NAME

        champion = get_user_model().objects.create_user(
            username="champ", email="champ@example.com", password="pw", corporation_affiliate=sponsor
        )
        champion.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        assert can_champion_jobs(champion)
        client.force_login(champion)
        assert client.get(self._create_url(sponsor)).status_code == 403

    def test_unknown_sponsor_is_404(self, client, manager):
        client.force_login(manager)
        assert client.get("/corporate-sponsors/999999/jobs/new/").status_code == 404

    def test_create_requires_csrf(self, manager, sponsor):
        from django.test import Client as DjangoClient

        csrf_client = DjangoClient(enforce_csrf_checks=True)
        csrf_client.force_login(manager)
        response = csrf_client.post(self._create_url(sponsor), self._form_data())
        assert response.status_code == 403
        assert not Job.objects.filter(title="One-off Role").exists()

    def test_sponsor_internals_are_not_on_the_form(self, client, manager, sponsor):
        sponsor.contract_amount = "987654.00"
        sponsor.primary_contact_name = "Secret Contact"
        sponsor.primary_contact_email = "secret@example.com"
        sponsor.save()
        client.force_login(manager)
        content = client.get(self._create_url(sponsor)).content.decode()
        for hidden in ("987654", "Secret Contact", "secret@example.com", "contract_amount"):
            assert hidden not in content, hidden

    def test_detail_page_links_to_the_create_form(self, client, manager, sponsor):
        client.force_login(manager)
        content = client.get(reverse("corporate-sponsors-detail", args=[sponsor.pk])).content.decode()
        assert reverse("corporate-sponsors-job-create", args=[sponsor.pk]) in content
        assert "Add a job" in content

    def test_job_does_not_leak_to_public_pages_when_draft(self, client, manager, sponsor):
        client.force_login(manager)
        client.post(self._create_url(sponsor), self._form_data(title="Draft Role"))
        assert "Draft Role" not in client.get(reverse("jobs-public-list")).content.decode()
