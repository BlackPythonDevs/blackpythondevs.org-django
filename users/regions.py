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
    "IO",
    "BI",
    "KM",
    "DJ",
    "ER",
    "ET",
    "TF",
    "KE",
    "MG",
    "MW",
    "MU",
    "YT",
    "MZ",
    "RE",
    "RW",
    "SC",
    "SO",
    "SS",
    "UG",
    "TZ",
    "ZM",
    "ZW",
}
MIDDLE_AFRICA = {"AO", "CM", "CF", "TD", "CG", "CD", "GQ", "GA", "ST"}
SOUTHERN_AFRICA = {"BW", "SZ", "LS", "NA", "ZA"}
WESTERN_AFRICA = {
    "BJ",
    "BF",
    "CV",
    "CI",
    "GM",
    "GH",
    "GN",
    "GW",
    "LR",
    "ML",
    "MR",
    "NE",
    "NG",
    "SH",
    "SN",
    "SL",
    "TG",
}

CARIBBEAN = {
    "AI",
    "AG",
    "AW",
    "BS",
    "BB",
    "BQ",
    "VG",
    "KY",
    "CU",
    "CW",
    "DM",
    "DO",
    "GD",
    "GP",
    "HT",
    "JM",
    "MQ",
    "MS",
    "PR",
    "BL",
    "KN",
    "LC",
    "MF",
    "VC",
    "SX",
    "TT",
    "TC",
    "VI",
}
CENTRAL_AMERICA = {"BZ", "CR", "SV", "GT", "HN", "MX", "NI", "PA"}
SOUTH_AMERICA = {"AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PY", "PE", "SR", "UY", "VE"}
NORTHERN_AMERICA = {"BM", "CA", "GL", "PM", "US"}

CENTRAL_ASIA = {"KZ", "KG", "TJ", "TM", "UZ"}
EASTERN_ASIA = {"CN", "HK", "MO", "MN", "KP", "KR", "JP", "TW"}
SOUTH_EASTERN_ASIA = {"BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"}
SOUTHERN_ASIA = {"AF", "BD", "BT", "IN", "IR", "MV", "NP", "PK", "LK"}
WESTERN_ASIA = {
    "AM",
    "AZ",
    "BH",
    "CY",
    "GE",
    "IQ",
    "IL",
    "JO",
    "KW",
    "LB",
    "OM",
    "PS",
    "QA",
    "SA",
    "SY",
    "TR",
    "AE",
    "YE",
}

EASTERN_EUROPE = {"BY", "BG", "CZ", "HU", "PL", "MD", "RO", "RU", "SK", "UA"}
NORTHERN_EUROPE = {
    "AX",
    "DK",
    "EE",
    "FO",
    "FI",
    "GG",
    "IS",
    "IE",
    "IM",
    "JE",
    "LV",
    "LT",
    "NO",
    "SJ",
    "SE",
    "GB",
}
SOUTHERN_EUROPE = {
    "AD",
    "AL",
    "BA",
    "HR",
    "GI",
    "GR",
    "VA",
    "IT",
    "MT",
    "ME",
    "MK",
    "PT",
    "SM",
    "RS",
    "SI",
    "ES",
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

# The four US Census Bureau regions (see `census_region_for_state` below)
# tacked onto the UN M49 list — not part of that geoscheme, but a person or
# community whose `state_province` resolves to one of these has that as
# their actual `region`, so staff need to be able to target it here too.
CENSUS_REGION_CHOICES = [
    ("US Northeast", "US Northeast"),
    ("US Midwest", "US Midwest"),
    ("US South", "US South"),
    ("US West", "US West"),
]

REGION_CHOICES = [(name, name) for name, _codes in _SUBREGIONS] + CENSUS_REGION_CHOICES

# The same subregions, grouped under their parent geoscheme region — for a
# checkbox list, Django renders each group as its own labelled cluster
# (`ChoiceWidget.optgroups` handles a nested list like this generically for
# CheckboxSelectMultiple, the same way it would <optgroup> a <select>).
GROUPED_REGION_CHOICES = [
    (
        "Africa",
        [
            ("Northern Africa", "Northern Africa"),
            ("Eastern Africa", "Eastern Africa"),
            ("Middle Africa", "Middle Africa"),
            ("Southern Africa", "Southern Africa"),
            ("Western Africa", "Western Africa"),
        ],
    ),
    (
        "Americas",
        [
            ("Caribbean", "Caribbean"),
            ("Central America", "Central America"),
            ("South America", "South America"),
            ("Northern America", "Northern America"),
            *CENSUS_REGION_CHOICES,
        ],
    ),
    (
        "Asia",
        [
            ("Central Asia", "Central Asia"),
            ("Eastern Asia", "Eastern Asia"),
            ("South-eastern Asia", "South-eastern Asia"),
            ("Southern Asia", "Southern Asia"),
            ("Western Asia", "Western Asia"),
        ],
    ),
    (
        "Europe",
        [
            ("Eastern Europe", "Eastern Europe"),
            ("Northern Europe", "Northern Europe"),
            ("Southern Europe", "Southern Europe"),
            ("Western Europe", "Western Europe"),
        ],
    ),
    (
        "Oceania",
        [
            ("Australia and New Zealand", "Australia and New Zealand"),
            ("Melanesia", "Melanesia"),
            ("Micronesia", "Micronesia"),
            ("Polynesia", "Polynesia"),
        ],
    ),
    ("Antarctica", [("Antarctica", "Antarctica")]),
]

# Same data, keyed by region name, for the clickable-map widget on the
# notification form — it needs to highlight every country in a subregion
# when just one of them is clicked.
SUBREGION_COUNTRIES = {name: sorted(codes) for name, codes in _SUBREGIONS}

# Parent region -> its subregion names, for the map widget's shift-click
# behaviour (select every subregion under one continent at once).
PARENT_REGIONS = {group: [name for name, _label in options] for group, options in GROUPED_REGION_CHOICES}

# The reverse of PARENT_REGIONS: subregion name -> its continent, for
# grouping a list of regions under continent headers (elections' ballot
# and results pages). Anything not in here — "Unspecified region", "Online",
# or any other value that isn't one of this taxonomy's subregions — falls
# back to OTHER_CONTINENT rather than raising.
REGION_TO_CONTINENT = {region: continent for continent, regions in PARENT_REGIONS.items() for region in regions}
OTHER_CONTINENT = "Other"


def continent_for_region(region):
    """The continent a subregion (as produced by `region_for_country` or
    `census_region_for_state`) belongs to, or `OTHER_CONTINENT` for
    anything outside this taxonomy."""
    return REGION_TO_CONTINENT.get(region, OTHER_CONTINENT)


def region_for_country(alpha2):
    """Return the UN M49 subregion name for an alpha-2 code, or "" if unmappable."""
    if not alpha2:
        return ""
    alpha2 = alpha2.upper()
    for name, codes in _SUBREGIONS:
        if alpha2 in codes:
            return name
    return ""


# US Census Bureau regions — the four top-level statistical regions, used to
# split NORTHERN_AMERICA's United States entry further once a user or
# community gives a `state_province` (see `User.save`/`Community.save`).
# Not part of the UN M49 geoscheme above (which never splits a country up);
# these apply only within the US and only once a state is actually known —
# an unrecognized or blank state leaves someone in the coarser "Northern
# America" bucket rather than erroring.
CENSUS_NORTHEAST = {"CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"}
CENSUS_MIDWEST = {"IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"}
CENSUS_SOUTH = {
    "DE",
    "FL",
    "GA",
    "MD",
    "NC",
    "SC",
    "VA",
    "DC",
    "WV",
    "AL",
    "KY",
    "MS",
    "TN",
    "AR",
    "LA",
    "OK",
    "TX",
}
CENSUS_WEST = {"AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"}

# "US" prefixed so, alongside plain "Northern America" and every other UN
# M49 subregion, it's unambiguous that these are the US-only Census split
# rather than some other place called "South" or "West".
_CENSUS_REGIONS = [
    ("US Northeast", CENSUS_NORTHEAST),
    ("US Midwest", CENSUS_MIDWEST),
    ("US South", CENSUS_SOUTH),
    ("US West", CENSUS_WEST),
]

# Full names for every abbreviation above (plus DC, treated as a state for
# this purpose), so "California" matches the same as "CA".
US_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
_NAME_TO_ABBR = {name.lower(): abbr for abbr, name in US_STATE_NAMES.items()}


def census_region_for_state(raw):
    """Match a free-text US state (2-letter abbreviation or full name, any
    case/whitespace) to one of the four Census Bureau regions above, or ""
    if it's blank or not recognized.

    `state_province` (`User`, `Community`) is free text so it also works
    for non-US provinces/regions used elsewhere (e.g. volunteer matching);
    this is the one place that specifically expects a US state and is
    forgiving about not finding one.
    """
    if not raw:
        return ""
    raw = raw.strip()
    abbr = raw.upper() if len(raw) == 2 else _NAME_TO_ABBR.get(raw.lower())
    if abbr not in US_STATE_NAMES:
        return ""
    for name, codes in _CENSUS_REGIONS:
        if abbr in codes:
            return name
    return ""
