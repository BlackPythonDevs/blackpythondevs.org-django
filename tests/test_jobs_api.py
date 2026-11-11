"""Key-authenticated jobs write API (issue #225).

Covers the security conditions on the issue: an unauthenticated write is
rejected without leaking job existence, a key can only write its own
sponsor's jobs, revocation immediately disables a key, no internal field can
be mass-assigned from the body, and ingested HTML is escaped when rendered.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone

from core.models import CORPORATE_SPONSOR_GROUP_NAME
from corporate_sponsorships.models import Sponsor
from jobs.models import JOB_CHAMPION_PERMS, Job, JobAPIKey, can_champion_jobs

pytestmark = pytest.mark.django_db

CREATE_URL = "/jobs/api/jobs/"


def _update_url(pk):
    return f"/jobs/api/jobs/{pk}/"


def _post(client, key, payload, **kwargs):
    return client.post(
        CREATE_URL,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {key}",
        **kwargs,
    )


@pytest.fixture
def sponsor(db):
    return Sponsor.objects.create(name="Acme Corp", url="https://acme.example.com")


@pytest.fixture
def other_sponsor(db):
    return Sponsor.objects.create(name="Rival Corp", url="https://rival.example.com")


@pytest.fixture
def issuer(db):
    return get_user_model().objects.create_user(username="issuer", email="issuer@example.com", password="pw")


@pytest.fixture
def key(sponsor, issuer):
    """Return ``(JobAPIKey, presented_plaintext)``."""
    return JobAPIKey.issue(sponsor, label="Feed push", created_by=issuer)


class TestAuthentication:
    def test_missing_key_rejected(self, client):
        response = client.post(CREATE_URL, data="{}", content_type="application/json")
        assert response.status_code == 401
        assert Job.objects.count() == 0

    def test_unknown_key_same_body_as_missing(self, client):
        missing = client.post(CREATE_URL, data="{}", content_type="application/json")
        unknown = client.post(
            CREATE_URL,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer totally-made-up-key",
        )
        assert unknown.status_code == 401
        # Same body and status as the no-key case: no key-existence oracle.
        assert unknown.content == missing.content

    def test_wrong_secret_rejected(self, client, key):
        _, presented = key
        key_id = presented.split(".", 1)[0]
        response = client.post(
            CREATE_URL,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {key_id}.not-the-secret",
        )
        assert response.status_code == 401
        assert Job.objects.count() == 0

    def test_inactive_key_rejected(self, client, key):
        obj, presented = key
        obj.active = False
        obj.save(update_fields=["active"])
        assert _post(client, presented, {"title": "x", "apply_url": "https://a.example.com"}).status_code == 401

    def test_expired_key_rejected(self, client, key):
        obj, presented = key
        obj.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        obj.save(update_fields=["expires_at"])
        assert _post(client, presented, {"title": "x", "apply_url": "https://a.example.com"}).status_code == 401

    def test_revoked_key_rejected(self, client, key):
        obj, presented = key
        obj.revoke()
        response = _post(client, presented, {"title": "x", "apply_url": "https://a.example.com"})
        assert response.status_code == 401
        assert Job.objects.count() == 0

    def test_x_api_key_header_works(self, client, key):
        _, presented = key
        response = client.post(
            CREATE_URL,
            data=json.dumps({"title": "Role", "apply_url": "https://a.example.com"}),
            content_type="application/json",
            HTTP_X_API_KEY=presented,
        )
        assert response.status_code == 201

    def test_get_method_not_allowed(self, client, key):
        _, presented = key
        response = client.get(CREATE_URL, HTTP_AUTHORIZATION=f"Bearer {presented}")
        assert response.status_code == 405


class TestCreate:
    def test_create_scopes_to_key_sponsor(self, client, key, sponsor, other_sponsor):
        _, presented = key
        response = _post(
            client,
            presented,
            {
                "title": "Backend Engineer",
                "apply_url": "https://acme.example.com/apply",
                "location": "Accra",
                "remote": True,
                "employment_type": Job.EMPLOYMENT_FULL_TIME,
            },
        )
        assert response.status_code == 201
        job = Job.objects.get()
        assert job.sponsor == sponsor
        assert job.sponsor != other_sponsor
        # New postings start as unpublished drafts, never self-published.
        assert job.status == Job.STATUS_DRAFT
        assert job.is_published is False

    def test_body_sponsor_is_rejected_not_ignored(self, client, key, sponsor, other_sponsor):
        _, presented = key
        response = _post(
            client,
            presented,
            {
                "title": "Role",
                "apply_url": "https://a.example.com",
                "sponsor": other_sponsor.pk,
            },
        )
        assert response.status_code == 400
        assert Job.objects.count() == 0

    @pytest.mark.parametrize(
        "field,value",
        [
            ("status", Job.STATUS_PUBLISHED),
            ("is_published", True),
            ("published_at", "2026-01-01T00:00:00Z"),
            ("source", "greenhouse"),
            ("external_id", "999"),
            ("id", 1),
            ("created_at", "2026-01-01T00:00:00Z"),
            ("updated_at", "2026-01-01T00:00:00Z"),
        ],
    )
    def test_internal_fields_rejected(self, client, key, field, value):
        _, presented = key
        response = _post(
            client,
            presented,
            {"title": "Role", "apply_url": "https://a.example.com", field: value},
        )
        assert response.status_code == 400
        assert Job.objects.count() == 0

    def test_unknown_field_rejected(self, client, key):
        _, presented = key
        response = _post(
            client,
            presented,
            {"title": "Role", "apply_url": "https://a.example.com", "salary": "lots"},
        )
        assert response.status_code == 400
        assert "salary" in response.json()["detail"]

    def test_missing_required_fields_rejected(self, client, key):
        _, presented = key
        assert _post(client, presented, {}).status_code == 400
        assert _post(client, presented, {"title": "Role"}).status_code == 400

    def test_title_max_length_enforced(self, client, key):
        _, presented = key
        response = _post(
            client,
            presented,
            {"title": "t" * 201, "apply_url": "https://a.example.com"},
        )
        assert response.status_code == 400

    def test_description_max_length_enforced(self, client, key):
        _, presented = key
        response = _post(
            client,
            presented,
            {"title": "Role", "apply_url": "https://a.example.com", "description": "x" * 20001},
        )
        assert response.status_code == 400

    def test_wrong_types_rejected(self, client, key):
        _, presented = key
        for payload in (
            {"title": 5, "apply_url": "https://a.example.com"},
            {"title": "Role", "apply_url": "https://a.example.com", "remote": "yes"},
            {"title": "Role", "apply_url": "https://a.example.com", "location": 7},
        ):
            assert _post(client, presented, payload).status_code == 400

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:text/html,hi",
            "//evil.example.com/apply",
            "not-a-url",
        ],
    )
    def test_apply_url_scheme_enforced(self, client, key, url):
        _, presented = key
        response = _post(client, presented, {"title": "Role", "apply_url": url})
        assert response.status_code == 400
        assert Job.objects.count() == 0

    def test_invalid_employment_type_rejected(self, client, key):
        _, presented = key
        response = _post(
            client,
            presented,
            {"title": "Role", "apply_url": "https://a.example.com", "employment_type": "wizard"},
        )
        assert response.status_code == 400

    def test_non_object_body_rejected(self, client, key):
        _, presented = key
        response = client.post(
            CREATE_URL,
            data="[1, 2, 3]",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {presented}",
        )
        assert response.status_code == 400

    def test_success_stamps_last_used(self, client, key):
        obj, presented = key
        assert obj.last_used is None
        _post(client, presented, {"title": "Role", "apply_url": "https://a.example.com"})
        obj.refresh_from_db()
        assert obj.last_used is not None

    def test_response_never_exposes_internal_fields_or_key(self, client, key, sponsor):
        _, presented = key
        response = _post(
            client,
            presented,
            {
                "title": "Role",
                "apply_url": "https://a.example.com",
                "location": "Accra",
            },
        )
        body = response.json()
        assert body["sponsor"] == sponsor.name
        for internal in ("status", "is_published", "source", "external_id", "created_at", "updated_at"):
            assert internal not in body
        # The plaintext key must never come back in any response.
        assert presented not in response.content.decode()


class TestUpdate:
    def _create(self, client, presented, **extra):
        payload = {"title": "Role", "apply_url": "https://a.example.com", **extra}
        response = _post(client, presented, payload)
        assert response.status_code == 201
        return response.json()["id"]

    def test_update_own_job(self, client, key):
        _, presented = key
        job_id = self._create(client, presented)
        response = client.put(
            _update_url(job_id),
            data=json.dumps({"title": "Senior Role", "location": "Lagos"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {presented}",
        )
        assert response.status_code == 200
        job = Job.objects.get(pk=job_id)
        assert job.title == "Senior Role"
        assert job.location == "Lagos"

    def test_update_other_sponsors_job_404(self, client, key, other_sponsor):
        _, presented = key
        foreign = Job.objects.create(title="Foreign", apply_url="https://rival.example.com/a", sponsor=other_sponsor)
        response = client.put(
            _update_url(foreign.pk),
            data=json.dumps({"title": "Hijacked"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {presented}",
        )
        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.title == "Foreign"

    def test_update_unknown_job_unauthenticated_401_not_404(self, client):
        """An anonymous probe must not learn whether a job exists."""
        assert client.put(_update_url(999999), data="{}", content_type="application/json").status_code == 401

    def test_update_unknown_job_authenticated_404(self, client, key):
        _, presented = key
        response = client.put(
            _update_url(999999),
            data='{"title": "x"}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {presented}",
        )
        assert response.status_code == 404

    def test_update_cannot_publish(self, client, key):
        _, presented = key
        job_id = self._create(client, presented)
        response = client.put(
            _update_url(job_id),
            data=json.dumps({"status": Job.STATUS_PUBLISHED, "is_published": True}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {presented}",
        )
        assert response.status_code == 400
        job = Job.objects.get(pk=job_id)
        assert job.is_published is False
        assert job.status == Job.STATUS_DRAFT


class TestChampionScope:
    """An out-of-scope champion cannot use the API key surface (#225)."""

    def test_out_of_scope_champion_is_not_authorised(self, client, other_sponsor, key):
        user = get_user_model().objects.create_user(
            username="champ",
            email="champ@example.com",
            password="pw",
            corporation_affiliate=other_sponsor,
            onboarding_completed_at=timezone.now(),
        )
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        client.force_login(user)
        _, presented = key
        # A logged-in session must not substitute for the API key.
        response = client.post(
            CREATE_URL,
            data=json.dumps({"title": "Role", "apply_url": "https://a.example.com"}),
            content_type="application/json",
        )
        assert response.status_code == 401
        # And a champion session cannot reach another sponsor's job via PUT.
        foreign = Job.objects.create(title="Acme Role", apply_url="https://acme.example.com/a", sponsor=key[0].sponsor)
        response = client.put(
            _update_url(foreign.pk),
            data=json.dumps({"title": "Hijack"}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_can_champion_jobs_still_true_for_valid_champion(self, other_sponsor):
        user = get_user_model().objects.create_user(
            username="champ2",
            email="champ2@example.com",
            password="pw",
            corporation_affiliate=other_sponsor,
            onboarding_completed_at=timezone.now(),
        )
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        user.user_permissions.add(*Permission.objects.filter(codename__in=JOB_CHAMPION_PERMS))
        assert can_champion_jobs(user) is True


class TestHtmlEscaping:
    def test_ingested_html_is_escaped_in_champion_view(self, client, key, sponsor):
        """A script payload stored via the API renders escaped, not executed."""
        _, presented = key
        payload = "<script>alert('xss')</script>"
        response = _post(
            client,
            presented,
            {"title": payload, "description": payload, "apply_url": "https://a.example.com"},
        )
        assert response.status_code == 201
        job = Job.objects.get()
        # Stored as plain text, not sanitised HTML.
        assert job.title == payload
        assert list(Job.objects.filter(title__contains="<script>")) == [job]

        # Rendering goes through autoescaping: the champion detail page shows
        # the escaped form, and the raw opening tag never appears.
        user = get_user_model().objects.create_user(
            username="champ3",
            email="champ3@example.com",
            password="pw",
            corporation_affiliate=sponsor,
            onboarding_completed_at=timezone.now(),
        )
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        user.user_permissions.add(*Permission.objects.filter(codename__in=JOB_CHAMPION_PERMS))
        client.force_login(user)
        page = client.get(reverse("jobs/manage-detail", args=[job.pk]))
        assert page.status_code == 200
        content = page.content.decode()
        assert "<script>alert('xss')</script>" not in content
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in content

    def test_ingested_html_escaped_on_public_page_after_publish(self, client, key, sponsor):
        _, presented = key
        payload = "<img src=x onerror=alert(1)>"
        _post(
            client,
            presented,
            {"title": payload, "description": payload, "apply_url": "https://a.example.com"},
        )
        job = Job.objects.get()
        job.status = Job.STATUS_PUBLISHED
        job.is_published = True
        job.published_at = timezone.now()
        job.save()
        content = client.get(reverse("jobs-public-detail", args=[job.pk])).content.decode()
        assert "<img src=x onerror=alert(1)>" not in content
        assert "&lt;img src=x onerror=alert(1)&gt;" in content


class TestKeyStorage:
    def test_plaintext_key_is_never_stored(self, sponsor, issuer):
        obj, presented = JobAPIKey.issue(sponsor, label="x", created_by=issuer)
        assert presented not in obj.key_hash
        # Only the id portion is stored in the clear (and it is not secret).
        assert obj.key_id in presented
        assert obj.key_hash != presented

    def test_verify_accepts_only_the_real_secret(self, sponsor, issuer):
        obj, presented = JobAPIKey.issue(sponsor, label="x", created_by=issuer)
        assert obj.verify(presented.split(".", 1)[1]) is True
        assert obj.verify("wrong") is False

    def test_revoke_marks_inactive_and_timestamps(self, sponsor, issuer):
        obj, _ = JobAPIKey.issue(sponsor, label="x", created_by=issuer)
        assert obj.is_active() is True
        obj.revoke()
        obj.refresh_from_db()
        assert obj.is_active() is False
        assert obj.revoked_at is not None

    def test_key_excluded_from_auditlog(self, settings):
        assert "jobs.JobAPIKey" in settings.AUDITLOG_EXCLUDE_TRACKING_MODELS

    def test_str_does_not_leak_hash(self, sponsor, issuer):
        obj, _ = JobAPIKey.issue(sponsor, label="My label", created_by=issuer)
        assert obj.key_hash not in str(obj)
        assert "My label" in str(obj)

    def test_admin_issues_a_hashed_key_and_revokes_it(self, client, sponsor):
        """The admin is the only issuing path; revoking disables the key."""
        admin = get_user_model().objects.create_superuser(username="root", email="root@example.com", password="pw")
        client.force_login(admin)
        url = reverse("admin:jobs_jobapikey_add")
        assert client.get(url).status_code == 200
        response = client.post(url, {"label": "feed", "sponsor": sponsor.pk, "active": "on"})
        assert response.status_code == 302
        obj = JobAPIKey.objects.get()
        assert obj.key_id
        assert obj.key_hash
        # Revoking through the admin action disables the key.
        obj.revoke()
        obj.refresh_from_db()
        assert obj.is_active() is False
        assert client.get(reverse("admin:jobs_jobapikey_change", args=[obj.pk])).status_code == 200
