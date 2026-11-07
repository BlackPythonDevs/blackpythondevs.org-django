"""The community map highlights countries computed from members and completed sponsored events (issue #207)."""

import datetime
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.urls import reverse

from core.map_data import MIN_MEMBERS_PER_COUNTRY, presence_countries
from event_sponsorships.models import SponsorshipRequest

pytestmark = pytest.mark.django_db


def make_members(country, n=MIN_MEMBERS_PER_COUNTRY, *, is_active=True, prefix=None):
    User = get_user_model()
    prefix = prefix or f"{country or 'blank'}{'' if is_active else '-inactive'}"
    for i in range(n):
        User.objects.create_user(
            username=f"{prefix}-{i}", email=f"{prefix}-{i}@example.com", country=country, is_active=is_active
        )


def make_event(country, status=SponsorshipRequest.COMPLETED):
    return SponsorshipRequest.objects.create(
        name=f"PyCon {country} {status}", start_date=datetime.date(2025, 5, 1), country=country, status=status
    )


def by_iso():
    return {c["iso_a3"]: c for c in presence_countries()}


def test_members_and_completed_events_are_highlighted():
    make_members("NG")
    make_members("GB")
    make_event("KE")
    make_event("NG")

    data = by_iso()

    assert set(data) == {"NGA", "GBR", "KEN"}
    assert data["NGA"] == {"iso_a3": "NGA", "name": "Nigeria", "has_members": True, "has_events": True}
    assert data["GBR"]["has_members"] and not data["GBR"]["has_events"]
    assert data["KEN"]["has_events"] and not data["KEN"]["has_members"]


@pytest.mark.parametrize(
    "status", [SponsorshipRequest.REQUESTED, SponsorshipRequest.APPROVED, SponsorshipRequest.CANCELLED]
)
def test_non_completed_events_are_left_out(status):
    make_event("KE", status=status)
    assert by_iso() == {}


def test_inactive_and_blank_country_members_are_left_out():
    make_members("GH", is_active=False)
    make_members("")
    assert by_iso() == {}


def test_countries_below_member_threshold_are_not_flagged():
    make_members("TG", n=MIN_MEMBERS_PER_COUNTRY - 1)
    assert "TGO" not in by_iso()

    make_event("TG")
    data = by_iso()
    assert data["TGO"]["has_events"] is True
    assert data["TGO"]["has_members"] is False


def test_view_embeds_presence_data_only(client):
    make_members("NG")
    make_event("KE")

    response = client.get(reverse("community-map"))

    assert response.status_code == 200
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert "max-age=86400" in response["Cache-Control"]
    html = response.content.decode()
    start = html.index('id="presence-countries"')
    payload = html[html.index(">", start) + 1 : html.index("</script>", start)]
    countries = json.loads(payload)
    assert {c["iso_a3"] for c in countries} == {"NGA", "KEN"}
    for c in countries:
        assert set(c) == {"iso_a3", "name", "has_members", "has_events"}
    assert "NG-0@example.com" not in html


def test_view_with_empty_database_renders(client):
    response = client.get(reverse("community-map"))
    assert response.status_code == 200
    assert response.context["presence_countries"] == []


def test_world_geojson_covers_presence_countries():
    path = finders.find("data/world-countries.geojson")
    assert path
    with open(path) as fh:
        data = json.load(fh)
    isos = {f["properties"]["ISO_A3"] for f in data["features"]}
    assert {"NGA", "GBR", "KEN", "USA", "FRA", "NOR", "BRA"} <= isos
