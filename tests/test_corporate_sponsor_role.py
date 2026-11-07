"""Corporate sponsorship roles (issue #203).

- The "Corporate Sponsorship Coordinator" group manages corporate sponsors
  only; the "Corporate Sponsor" group carries no permissions at all.
- A member tied to a sponsor via User.corporation_affiliate and in the
  "Corporate Sponsor" group sees that sponsor, and only that sponsor, at the
  read-only /corporate-sponsors/mine/ page.
- The affiliation can't be set through the member-facing forms.
- The first affiliate of a sponsor with no primary contact becomes it.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from core.models import (
    CORPORATE_SPONSOR_GROUP_NAME,
    CORPORATE_SPONSORSHIP_COORDINATOR_GROUP_NAME,
    is_corporate_sponsor,
)
from corporate_sponsorships.models import Sponsor

pytestmark = pytest.mark.django_db

MINE = "/corporate-sponsors/mine/"


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
    return Sponsor.objects.create(
        name="Own Corp",
        url="https://own.example.com",
        invoice_paid_date=date(2026, 1, 15),
        contract_amount=Decimal("98765.43"),
        primary_contact_name="Existing Contact",
        primary_contact_email="contact@own.example.com",
    )


@pytest.fixture
def other_sponsor(db):
    return Sponsor.objects.create(name="Other Corp", contract_amount=Decimal("55555.00"))


@pytest.fixture
def sponsor_user(own_sponsor):
    user = _user("sponsoruser", corporation_affiliate=own_sponsor)
    user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
    return user


@pytest.fixture
def coordinator(db):
    user = _user("coordinator")
    user.groups.add(Group.objects.get(name=CORPORATE_SPONSORSHIP_COORDINATOR_GROUP_NAME))
    return user


class TestGroups:
    def test_coordinator_group_has_exactly_the_sponsor_perms(self):
        group = Group.objects.get(name=CORPORATE_SPONSORSHIP_COORDINATOR_GROUP_NAME)
        perms = set(group.permissions.values_list("content_type__app_label", "codename"))
        assert perms == {
            ("corporate_sponsorships", "view_sponsor"),
            ("corporate_sponsorships", "add_sponsor"),
            ("corporate_sponsorships", "change_sponsor"),
            ("corporate_sponsorships", "delete_sponsor"),
        }

    def test_corporate_sponsor_group_has_no_perms(self):
        group = Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME)
        assert not group.permissions.exists()

    def test_not_the_notifications_sponsors_group(self):
        assert CORPORATE_SPONSOR_GROUP_NAME != "Sponsors"


class TestCoordinator:
    def test_reaches_corporate_console_not_event_console(self, client, coordinator, own_sponsor):
        client.force_login(coordinator)
        assert client.get("/corporate-sponsors/").status_code == 200
        assert client.get(f"/corporate-sponsors/{own_sponsor.pk}/").status_code == 200
        assert client.get("/event-sponsorships/").status_code == 403

    def test_sees_corporate_card_not_event_card(self, client, coordinator):
        client.force_login(coordinator)
        content = client.get("/members/").content.decode()
        assert 'href="/corporate-sponsors/"' in content
        assert 'href="/event-sponsorships/"' not in content


class TestMySponsorshipPage:
    def test_anonymous_is_sent_to_login(self, client):
        response = client.get(MINE)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_shows_own_sponsor_allowlisted_fields_only(self, client, sponsor_user, own_sponsor, other_sponsor):
        client.force_login(sponsor_user)
        response = client.get(MINE)
        assert response.status_code == 200
        assert "corporate_sponsorships/sponsor_detail.html" not in [t.name for t in response.templates]
        content = response.content.decode()
        assert "Own Corp" in content
        assert "https://own.example.com" in content
        assert "15 Jan 2027" in content  # expires_at
        assert "Active" in content
        # Internal fields and other sponsors never render.
        for hidden in ("98765", "Existing Contact", "contact@own.example.com", "Other Corp", "55555"):
            assert hidden not in content, hidden
        assert "Invoice paid" not in content
        assert "Contract amount" not in content
        assert "checklist" not in content.lower()

    def test_query_params_cannot_pick_another_sponsor(self, client, sponsor_user, other_sponsor):
        client.force_login(sponsor_user)
        content = client.get(MINE, {"pk": other_sponsor.pk, "id": other_sponsor.pk}).content.decode()
        assert "Other Corp" not in content
        assert "Own Corp" in content

    def test_post_is_not_allowed(self, client, sponsor_user):
        client.force_login(sponsor_user)
        assert client.post(MINE).status_code == 405

    def test_group_without_affiliation_gets_404(self, client):
        user = _user("noaffil")
        user.groups.add(Group.objects.get(name=CORPORATE_SPONSOR_GROUP_NAME))
        client.force_login(user)
        assert client.get(MINE).status_code == 404

    def test_affiliation_without_group_gets_404(self, client, own_sponsor):
        client.force_login(_user("nogroup", corporation_affiliate=own_sponsor))
        assert client.get(MINE).status_code == 404

    def test_ordinary_member_gets_404(self, client):
        client.force_login(_user("member"))
        assert client.get(MINE).status_code == 404

    def test_superuser_without_affiliation_gets_404(self, client):
        admin = get_user_model().objects.create_superuser(username="admin", email="admin@example.com", password="pw")
        client.force_login(admin)
        assert client.get(MINE).status_code == 404

    def test_helper(self, sponsor_user):
        from django.contrib.auth.models import AnonymousUser

        assert is_corporate_sponsor(sponsor_user)
        assert not is_corporate_sponsor(AnonymousUser())


class TestSponsorUserIsolation:
    def test_denied_every_corporate_crud_route(self, client, sponsor_user, own_sponsor, other_sponsor):
        client.force_login(sponsor_user)
        urls = ["/corporate-sponsors/", "/corporate-sponsors/new/"]
        for sponsor in (own_sponsor, other_sponsor):
            urls += [
                f"/corporate-sponsors/{sponsor.pk}/",
                f"/corporate-sponsors/{sponsor.pk}/edit/",
                f"/corporate-sponsors/{sponsor.pk}/delete/",
            ]
        for url in urls:
            assert client.get(url).status_code in (403, 404), url
            assert client.post(url, {"name": "Hijacked"}).status_code in (403, 404), url
        assert not Sponsor.objects.filter(name="Hijacked").exists()
        assert Sponsor.objects.filter(pk=other_sponsor.pk).exists()

    def test_denied_event_console(self, client, sponsor_user):
        client.force_login(sponsor_user)
        assert client.get("/event-sponsorships/").status_code in (403, 404)
        assert client.get("/event-sponsorships/new/").status_code in (403, 404)

    def test_member_area_links_to_my_sponsorship(self, client, sponsor_user):
        client.force_login(sponsor_user)
        content = client.get("/members/").content.decode()
        assert f'href="{MINE}"' in content
        assert 'href="/corporate-sponsors/"' not in content

    def test_ordinary_member_has_no_my_sponsorship_link(self, client):
        client.force_login(_user("member"))
        assert f'href="{MINE}"' not in client.get("/members/").content.decode()


class TestAffiliationNotSelfServe:
    def _form_data(self):
        return {
            "display_name": "Member",
            "member_type": "member",
            "country": "US",
            "state_province": "",
        }

    @pytest.mark.parametrize("url", ["/profile/", "/onboarding/"])
    def test_posting_affiliation_is_ignored(self, client, url, other_sponsor):
        user = _user("member")
        client.force_login(user)
        data = {**self._form_data(), "corporation_affiliate": other_sponsor.pk}
        response = client.post(url, data)
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.display_name == "Member"  # the form did save
        assert user.corporation_affiliate is None

    @pytest.mark.parametrize("url", ["/profile/", "/onboarding/"])
    def test_posting_cannot_change_existing_affiliation(self, client, url, sponsor_user, own_sponsor, other_sponsor):
        client.force_login(sponsor_user)
        client.post(url, {**self._form_data(), "corporation_affiliate": other_sponsor.pk})
        sponsor_user.refresh_from_db()
        assert sponsor_user.corporation_affiliate_id == own_sponsor.pk

    def test_affiliation_absent_from_member_forms(self):
        from users.forms import CouncilProfileForm, OnboardingForm, ProfileForm, SignupForm

        for form in (OnboardingForm, ProfileForm, CouncilProfileForm, SignupForm):
            assert "corporation_affiliate" not in form.base_fields, form


class TestPrimaryContactAutofill:
    def test_first_affiliate_fills_empty_contact(self, other_sponsor):
        user = _user("first", display_name="First Affiliate")
        user.corporation_affiliate = other_sponsor
        user.save()
        other_sponsor.refresh_from_db()
        assert other_sponsor.primary_contact_email == "first@example.com"
        assert other_sponsor.primary_contact_name == "First Affiliate"
        assert other_sponsor.primary_contact_user == user
        assert other_sponsor.contract_amount == Decimal("55555.00")

    def test_second_affiliate_does_not_overwrite(self, other_sponsor):
        first = _user("first", corporation_affiliate=other_sponsor)
        _user("second", corporation_affiliate=other_sponsor)
        other_sponsor.refresh_from_db()
        assert other_sponsor.primary_contact_user == first
        assert other_sponsor.primary_contact_email == "first@example.com"

    def test_existing_contact_is_never_overwritten(self, own_sponsor):
        _user("newcomer", corporation_affiliate=own_sponsor)
        own_sponsor.refresh_from_db()
        assert own_sponsor.primary_contact_email == "contact@own.example.com"
        assert own_sponsor.primary_contact_name == "Existing Contact"

    def test_deleting_sponsor_clears_affiliation(self, sponsor_user, own_sponsor):
        own_sponsor.delete()
        sponsor_user.refresh_from_db()
        assert sponsor_user.corporation_affiliate is None
