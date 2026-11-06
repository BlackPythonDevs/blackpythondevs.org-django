"""Map an ISO 3166-1 alpha-2 country code to the region used for grouping.

"Region" here is the continent name (Africa, North America, South America,
Europe, Asia, Oceania) — the same buckets the public events page has always
grouped sponsorships into. The lookup goes through pycountry-convert so we don't
hand-maintain a 250-row country table.
"""

from pycountry_convert import (
    convert_continent_code_to_continent_name,
    country_alpha2_to_continent_code,
)


def region_for_country(alpha2):
    """Return the continent name for an alpha-2 code, or "" if unmappable.

    A handful of territories (e.g. Antarctica, some dependencies) have no
    continent mapping in pycountry-convert; those return "" so the caller can
    fall back to whatever region is already stored.
    """
    if not alpha2:
        return ""
    try:
        return convert_continent_code_to_continent_name(country_alpha2_to_continent_code(alpha2))
    except (KeyError, ValueError):
        return ""
