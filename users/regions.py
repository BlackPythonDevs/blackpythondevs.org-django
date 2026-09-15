"""Map an ISO 3166-1 alpha-2 country code to its UN M49 geoscheme subregion.

This is the standard UN statistical geoscheme
(https://unstats.un.org/unsd/methodology/m49/) rather than a BPD-invented
grouping: every country falls into one of its 22 subregions (Africa and Asia
split five ways, the Americas and Europe split four ways, Oceania split four
ways). A handful of uninhabited or disputed territories the scheme doesn't
cover fall back to "Antarctica" or "" — see `region_for_country`.
"""

# Leaf subregions of the UN M49 geoscheme, keyed by ISO 3166-1 alpha-2 code.
# Order matches the geoscheme's own region -> subregion grouping.
NORTHERN_AFRICA = {"DZ", "EG", "LY", "MA", "SD", "TN", "EH"}
EASTERN_AFRICA = {
    "IO", "BI", "KM", "DJ", "ER", "ET", "TF", "KE", "MG", "MW",
    "MU", "YT", "MZ", "RE", "RW", "SC", "SO", "SS", "UG", "TZ", "ZM", "ZW",
}
MIDDLE_AFRICA = {"AO", "CM", "CF", "TD", "CG", "CD", "GQ", "GA", "ST"}
SOUTHERN_AFRICA = {"BW", "SZ", "LS", "NA", "ZA"}
WESTERN_AFRICA = {
    "BJ", "BF", "CV", "CI", "GM", "GH", "GN", "GW", "LR", "ML",
    "MR", "NE", "NG", "SH", "SN", "SL", "TG",
}

CARIBBEAN = {
    "AI", "AG", "AW", "BS", "BB", "BQ", "VG", "KY", "CU", "CW",
    "DM", "DO", "GD", "GP", "HT", "JM", "MQ", "MS", "PR", "BL",
    "KN", "LC", "MF", "VC", "SX", "TT", "TC", "VI",
}
CENTRAL_AMERICA = {"BZ", "CR", "SV", "GT", "HN", "MX", "NI", "PA"}
SOUTH_AMERICA = {"AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PY", "PE", "SR", "UY", "VE"}
NORTHERN_AMERICA = {"BM", "CA", "GL", "PM", "US"}

CENTRAL_ASIA = {"KZ", "KG", "TJ", "TM", "UZ"}
EASTERN_ASIA = {"CN", "HK", "MO", "MN", "KP", "KR", "JP", "TW"}
SOUTH_EASTERN_ASIA = {"BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"}
SOUTHERN_ASIA = {"AF", "BD", "BT", "IN", "IR", "MV", "NP", "PK", "LK"}
WESTERN_ASIA = {
    "AM", "AZ", "BH", "CY", "GE", "IQ", "IL", "JO", "KW", "LB",
    "OM", "PS", "QA", "SA", "SY", "TR", "AE", "YE",
}

EASTERN_EUROPE = {"BY", "BG", "CZ", "HU", "PL", "MD", "RO", "RU", "SK", "UA"}
NORTHERN_EUROPE = {
    "AX", "DK", "EE", "FO", "FI", "GG", "IS", "IE", "IM", "JE",
    "LV", "LT", "NO", "SJ", "SE", "GB",
}
SOUTHERN_EUROPE = {
    "AD", "AL", "BA", "HR", "GI", "GR", "VA", "IT", "MT", "ME",
    "MK", "PT", "SM", "RS", "SI", "ES",
}
WESTERN_EUROPE = {"AT", "BE", "FR", "DE", "LI", "LU", "MC", "NL", "CH"}

AUSTRALIA_AND_NEW_ZEALAND = {"AU", "NZ", "NF"}
MELANESIA = {"FJ", "NC", "PG", "SB", "VU"}
MICRONESIA = {"GU", "KI", "MH", "FM", "NR", "MP", "PW"}
POLYNESIA = {"AS", "CK", "PF", "NU", "PN", "WS", "TK", "TO", "TV", "WF"}

# Uninhabited or research-only territories the geoscheme doesn't assign.
ANTARCTIC = {"AQ", "BV", "GS", "HM", "UM"}

_SUBREGIONS = [
    ("Northern Africa", NORTHERN_AFRICA),
    ("Eastern Africa", EASTERN_AFRICA),
    ("Middle Africa", MIDDLE_AFRICA),
    ("Southern Africa", SOUTHERN_AFRICA),
    ("Western Africa", WESTERN_AFRICA),
    ("Caribbean", CARIBBEAN),
    ("Central America", CENTRAL_AMERICA),
    ("South America", SOUTH_AMERICA),
    ("Northern America", NORTHERN_AMERICA),
    ("Central Asia", CENTRAL_ASIA),
    ("Eastern Asia", EASTERN_ASIA),
    ("South-eastern Asia", SOUTH_EASTERN_ASIA),
    ("Southern Asia", SOUTHERN_ASIA),
    ("Western Asia", WESTERN_ASIA),
    ("Eastern Europe", EASTERN_EUROPE),
    ("Northern Europe", NORTHERN_EUROPE),
    ("Southern Europe", SOUTHERN_EUROPE),
    ("Western Europe", WESTERN_EUROPE),
    ("Australia and New Zealand", AUSTRALIA_AND_NEW_ZEALAND),
    ("Melanesia", MELANESIA),
    ("Micronesia", MICRONESIA),
    ("Polynesia", POLYNESIA),
    ("Antarctica", ANTARCTIC),
]

REGION_CHOICES = [(name, name) for name, _codes in _SUBREGIONS]

# The same subregions, grouped under their parent geoscheme region — for a
# checkbox list, Django renders each group as its own labelled cluster
# (`ChoiceWidget.optgroups` handles a nested list like this generically for
# CheckboxSelectMultiple, the same way it would <optgroup> a <select>).
GROUPED_REGION_CHOICES = [
    ("Africa", [
        ("Northern Africa", "Northern Africa"),
        ("Eastern Africa", "Eastern Africa"),
        ("Middle Africa", "Middle Africa"),
        ("Southern Africa", "Southern Africa"),
        ("Western Africa", "Western Africa"),
    ]),
    ("Americas", [
        ("Caribbean", "Caribbean"),
        ("Central America", "Central America"),
        ("South America", "South America"),
        ("Northern America", "Northern America"),
    ]),
    ("Asia", [
        ("Central Asia", "Central Asia"),
        ("Eastern Asia", "Eastern Asia"),
        ("South-eastern Asia", "South-eastern Asia"),
        ("Southern Asia", "Southern Asia"),
        ("Western Asia", "Western Asia"),
    ]),
    ("Europe", [
        ("Eastern Europe", "Eastern Europe"),
        ("Northern Europe", "Northern Europe"),
        ("Southern Europe", "Southern Europe"),
        ("Western Europe", "Western Europe"),
    ]),
    ("Oceania", [
        ("Australia and New Zealand", "Australia and New Zealand"),
        ("Melanesia", "Melanesia"),
        ("Micronesia", "Micronesia"),
        ("Polynesia", "Polynesia"),
    ]),
    ("Antarctica", [("Antarctica", "Antarctica")]),
]

# Same data, keyed by region name, for the clickable-map widget on the
# notification form — it needs to highlight every country in a subregion
# when just one of them is clicked.
SUBREGION_COUNTRIES = {name: sorted(codes) for name, codes in _SUBREGIONS}

# Parent region -> its subregion names, for the map widget's shift-click
# behaviour (select every subregion under one continent at once).
PARENT_REGIONS = {group: [name for name, _label in options] for group, options in GROUPED_REGION_CHOICES}


def region_for_country(alpha2):
    """Return the UN M49 subregion name for an alpha-2 code, or "" if unmappable."""
    if not alpha2:
        return ""
    alpha2 = alpha2.upper()
    for name, codes in _SUBREGIONS:
        if alpha2 in codes:
            return name
    return ""
