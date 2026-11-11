"""Community partners: the public /community-partners/ page (#234).

A read-only Django (non-Wagtail) page listing active community partners.
The view projects each row through CommunityPartner.PUBLIC_FIELDS, so these
tests assert both the happy path and that internal fields (notes, timestamps)
never reach the rendered page.
"""

import pytest
from django.urls import reverse

from community_partners.models import CommunityPartner

pytestmark = pytest.mark.django_db


@pytest.fixture
def partner(db):
    return CommunityPartner.objects.create(
        name="PyLagos",
        description="A Python community in Lagos.",
        website="https://pylagos.example/",
        logo_static_path="images/pylagos.webp",
    )


class TestPublicPage:
    def test_url_is_reachable(self, client):
        response = client.get(reverse("community-partners"))
        assert response.status_code == 200

    def test_lists_active_partner(self, client, partner):
        response = client.get(reverse("community-partners"))
        content = response.content.decode()
        assert "PyLagos" in content
        assert "A Python community in Lagos." in content
        assert "https://pylagos.example/" in content
        assert "images/pylagos.webp" in content

    def test_hides_inactive_partner(self, client, partner):
        CommunityPartner.objects.create(name="Hidden Community", is_active=False)
        response = client.get(reverse("community-partners"))
        assert "Hidden Community" not in response.content.decode()

    def test_orders_by_sort_order_then_name(self, client, db):
        CommunityPartner.objects.create(name="Zeta", sort_order=1)
        CommunityPartner.objects.create(name="Alpha", sort_order=1)
        CommunityPartner.objects.create(name="First", sort_order=0)
        response = client.get(reverse("community-partners"))
        content = response.content.decode()
        assert content.index("First") < content.index("Alpha") < content.index("Zeta")

    def test_never_renders_internal_notes(self, client, partner):
        partner.notes = "INTERNAL-ONLY-NOTE"
        partner.save()
        response = client.get(reverse("community-partners"))
        assert "INTERNAL-ONLY-NOTE" not in response.content.decode()

    def test_empty_state(self, client, db):
        response = client.get(reverse("community-partners"))
        assert response.status_code == 200
        assert b"between partners" in response.content

    def test_rejects_non_safe_methods(self, client, db):
        response = client.post(reverse("community-partners"))
        assert response.status_code == 405


class TestPublicData:
    def test_get_public_data_excludes_notes(self, partner):
        partner.notes = "secret"
        data = partner.get_public_data()
        assert "notes" not in data
        assert set(data) == set(CommunityPartner.PUBLIC_FIELDS)
