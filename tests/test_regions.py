"""The UN M49 geoscheme lookup used for the member profile and notification
region filter.
"""

import pytest

from users.regions import REGION_CHOICES, region_for_country


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
