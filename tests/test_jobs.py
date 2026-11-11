"""Jobs app: Job model storage, URL validation, admin, and #222 allowlists."""

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from corporate_sponsorships.models import Sponsor
from jobs.admin import JobAdmin
from jobs.models import Job

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
