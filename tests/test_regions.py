"""The UN M49 geoscheme lookup used for the member profile and notification
region filter.
"""

import pytest

from users.regions import REGION_CHOICES, census_region_for_state, continent_for_region, region_for_country


@pytest.mark.parametrize(
    "alpha2,expected",
    [
        ("NG", "Western Africa"),
        ("GH", "Western Africa"),
        ("KE", "Eastern Africa"),
        ("ET", "Eastern Africa"),
        ("CM", "Middle Africa"),
        ("CD", "Middle Africa"),
        ("ZA", "Southern Africa"),
        ("BW", "Southern Africa"),
        ("EG", "Northern Africa"),
        ("SD", "Northern Africa"),
        ("JM", "Caribbean"),
        ("MX", "Central America"),
        ("BR", "South America"),
        ("US", "Northern America"),
        ("CA", "Northern America"),
        ("KZ", "Central Asia"),
        ("JP", "Eastern Asia"),
        ("VN", "South-eastern Asia"),
        ("IN", "Southern Asia"),
        ("IR", "Southern Asia"),
        ("TR", "Western Asia"),
        ("IL", "Western Asia"),
        ("SA", "Western Asia"),
        ("RU", "Eastern Europe"),
        ("GB", "Northern Europe"),
        ("SE", "Northern Europe"),
        ("ES", "Southern Europe"),
        ("DE", "Western Europe"),
        ("FR", "Western Europe"),
        ("AU", "Australia and New Zealand"),
        ("FJ", "Melanesia"),
        ("GU", "Micronesia"),
        ("WS", "Polynesia"),
        ("AQ", "Antarctica"),
    ],
)
def test_region_for_country(alpha2, expected):
    assert region_for_country(alpha2) == expected


def test_blank_code_is_unmapped():
    assert region_for_country("") == ""


def test_every_choice_is_reachable():
    """Every value offered in the filter UI should be something a real
    country can actually resolve to — otherwise it's dead weight in the form."""
    reachable = {name for name, _ in REGION_CHOICES}
    produced = {
        region_for_country(code)
        for code in [
            "NG",
            "KE",
            "CM",
            "ZA",
            "EG",
            "JM",
            "MX",
            "BR",
            "US",
            "KZ",
            "JP",
            "VN",
            "IN",
            "TR",
            "RU",
            "GB",
            "ES",
            "DE",
            "AU",
            "FJ",
            "GU",
            "WS",
            "AQ",
        ]
    }
    assert produced <= reachable


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("NY", "US Northeast"),
        ("ny", "US Northeast"),
        ("New York", "US Northeast"),
        ("new york", "US Northeast"),
        ("  NY  ", "US Northeast"),
        ("IL", "US Midwest"),
        ("Illinois", "US Midwest"),
        ("TX", "US South"),
        ("Texas", "US South"),
        ("DC", "US South"),
        ("District of Columbia", "US South"),
        ("CA", "US West"),
        ("California", "US West"),
    ],
)
def test_census_region_for_state(raw, expected):
    assert census_region_for_state(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "Ontario", "Ceylon", "XX", "  "])
def test_census_region_for_state_unrecognized_is_blank(raw):
    assert census_region_for_state(raw) == ""


@pytest.mark.django_db
class TestUserRegionDerivation:
    def make_user(self, username, **kwargs):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(username=username, email=f"{username}@example.com", **kwargs)

    def test_us_state_narrows_region_to_a_census_region(self):
        user = self.make_user("atlanta", country="US", state_province="GA")
        assert user.region == "US South"

    def test_unrecognized_us_state_falls_back_to_northern_america(self):
        user = self.make_user("mystery", country="US", state_province="")
        assert user.region == "Northern America"

    def test_non_us_country_ignores_state_province(self):
        user = self.make_user("toronto", country="CA", state_province="Ontario")
        assert user.region == "Northern America"


@pytest.mark.parametrize(
    "region,continent",
    [
        ("Western Africa", "Africa"),
        ("Northern America", "Americas"),
        ("South-eastern Asia", "Asia"),
        ("Western Europe", "Europe"),
        ("Polynesia", "Oceania"),
        ("Antarctica", "Antarctica"),
        # The US Census regions live under "Americas" alongside the UN
        # subregions, not off on their own.
        ("US Northeast", "Americas"),
        ("US Midwest", "Americas"),
        ("US South", "Americas"),
        ("US West", "Americas"),
    ],
)
def test_continent_for_region(region, continent):
    assert continent_for_region(region) == continent


def test_continent_for_unrecognized_region_falls_back_to_other():
    assert continent_for_region("Unspecified region") == "Other"
    assert continent_for_region("") == "Other"
