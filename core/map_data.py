"""Country presence data for the public community map (/community-map/).

The map highlights every country where Black Python Devs has members or has
sponsored a completed event. Only presence flags leave this module — never
counts, names or other member details — and a country is only flagged for
members once it reaches ``MIN_MEMBERS_PER_COUNTRY``, so a highlighted country
can't single out one or two people.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count
from django_countries import countries

from event_sponsorships.models import SponsorshipRequest

# A country is shown as having members only once at least this many active
# members live there.
MIN_MEMBERS_PER_COUNTRY = 3


def member_countries() -> set[str]:
    """ISO alpha-2 codes of countries with at least MIN_MEMBERS_PER_COUNTRY active members."""
    rows = (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(country="")
        .values("country")
        .annotate(n=Count("pk"))
        .filter(n__gte=MIN_MEMBERS_PER_COUNTRY)
        .values_list("country", flat=True)
    )
    return set(rows)


def event_countries() -> set[str]:
    """ISO alpha-2 codes of countries that hosted a completed sponsored event."""
    rows = (
        SponsorshipRequest.objects.filter(status=SponsorshipRequest.COMPLETED)
        .exclude(country="")
        .values_list("country", flat=True)
        .distinct()
    )
    return set(rows)


def presence_countries() -> list[dict]:
    """Countries to highlight, as ``{iso_a3, name, has_members, has_events}`` dicts sorted by name."""
    members = member_countries()
    events = event_countries()
    result = []
    for code in members | events:
        iso_a3 = countries.alpha3(code)
        if not iso_a3:
            continue
        result.append(
            {
                "iso_a3": iso_a3,
                "name": str(countries.name(code)),
                "has_members": code in members,
                "has_events": code in events,
            }
        )
    return sorted(result, key=lambda c: c["name"])
