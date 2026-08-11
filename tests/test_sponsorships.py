"""The two sponsorship surfaces: the Executor console and the public intake form.

The neapolitan CRUDView at /sponsorships/ is a management console — it demands
the full add/change/delete/view set, so ordinary members and anonymous visitors
are bounced. The form at /sponsorships/request/ is the opposite: open to anyone,
since the organisers who need it come from outside the community.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from sponsorships.models import SponsorshipRequest

pytestmark = pytest.mark.django_db

CONSOLE_URLS = ["/sponsorships/", "/sponsorships/new/"]
DETAIL_URLS = ["/sponsorships/{pk}/", "/sponsorships/{pk}/edit/", "/sponsorships/{pk}/delete/"]


@pytest.fixture
def sponsorship(db):
    return SponsorshipRequest.objects.create(
        name="PyCon Somewhere",
        start_date=datetime.date(2026, 5, 1),
        country="NG",
    )


@pytest.fixture
def executor(db):
    user = get_user_model().objects.create_user(
        username="exec", email="exec@example.com", password="pw"
    )
    user.groups.add(Group.objects.get(name="Executor"))
    return user


@pytest.fixture
def member(db):
    return get_user_model().objects.create_user(
        username="member", email="member@example.com", password="pw"
    )


def all_urls(sponsorship):
    return CONSOLE_URLS + [u.format(pk=sponsorship.pk) for u in DETAIL_URLS]


class TestConsoleAccess:
    def test_executor_reaches_every_view(self, client, executor, sponsorship):
        client.force_login(executor)
        for url in all_urls(sponsorship):
            assert client.get(url).status_code == 200, url

    def test_anonymous_is_bounced(self, client, sponsorship):
        for url in all_urls(sponsorship):
            assert client.get(url).status_code == 302, url

    def test_ordinary_member_gets_403(self, client, member, sponsorship):
        """Signed in but unprivileged: 403, not a pointless bounce to login.

        This is PermissionRequiredMixin's own split — it redirects anonymous
        users and raises for authenticated ones.
        """
        client.force_login(member)
        for url in all_urls(sponsorship):
            assert client.get(url).status_code == 403, url


class TestConsoleTemplates:
    """The site's own templates must win over neapolitan's Tailwind defaults."""

    def test_site_templates_are_used(self, client, executor, sponsorship):
        client.force_login(executor)
        expected = {
            "/sponsorships/": "sponsorships/sponsorshiprequest_list.html",
            "/sponsorships/new/": "sponsorships/sponsorshiprequest_form.html",
            f"/sponsorships/{sponsorship.pk}/": "sponsorships/sponsorshiprequest_detail.html",
            f"/sponsorships/{sponsorship.pk}/edit/": "sponsorships/sponsorshiprequest_form.html",
            f"/sponsorships/{sponsorship.pk}/delete/": "sponsorships/sponsorshiprequest_confirm_delete.html",
        }
        for url, template in expected.items():
            names = [t.name for t in client.get(url).templates if t.name]
            assert template in names, f"{url} rendered {names}"

    def test_detail_shows_staff_only_fields(self, client, executor, sponsorship):
        sponsorship.notes = "Chased the organiser twice."
        sponsorship.save()
        client.force_login(executor)
        body = client.get(f"/sponsorships/{sponsorship.pk}/").content.decode()
        assert "Chased the organiser twice." in body
        assert "Internal notes" in body


class TestConsoleWrites:
    def test_executor_can_create_and_derived_fields_are_set(self, client, executor):
        client.force_login(executor)
        response = client.post(
            "/sponsorships/new/",
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
        assert client.post(f"/sponsorships/{sponsorship.pk}/delete/").status_code == 302
        assert not SponsorshipRequest.objects.filter(pk=sponsorship.pk).exists()

    def test_anonymous_cannot_create(self, client):
        client.post(
            "/sponsorships/new/",
            {"name": "Sneaky", "start_date": "2027-01-01", "country": "US"},
        )
        assert not SponsorshipRequest.objects.filter(name="Sneaky").exists()


class TestPublicIntake:
    def test_anonymous_can_open_the_form(self, client):
        response = client.get("/sponsorships/request/")
        assert response.status_code == 200
        assert "sponsorships/request_form.html" in [t.name for t in response.templates if t.name]

    def test_internal_notes_are_not_exposed(self, client):
        form = client.get("/sponsorships/request/").context["form"]
        assert "notes" not in form.fields
        assert "status" not in form.fields
        assert "paid" not in form.fields

    def test_submission_creates_a_requested_record(self, client):
        response = client.post(
            "/sponsorships/request/",
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

    def test_thanks_page_renders(self, client):
        assert client.get("/sponsorships/request/thanks/").status_code == 200

    def test_intake_url_is_not_swallowed_by_the_detail_route(self, client):
        """`request/` must not be read as a CRUD pk lookup."""
        response = client.get("/sponsorships/request/")
        assert response.resolver_match.url_name == "sponsorship-request"
