"""Sponsored events: only completed ones publish; unpaid ones get a badge."""

import pytest

from events.models import EventIndexPage
from sponsorships.models import SponsorshipRequest

pytestmark = pytest.mark.django_db


@pytest.fixture
def events_index(site):
    return EventIndexPage.objects.get()


def make(index, name, **kwargs):
    defaults = {"year": 2025, "region": "Africa", "status": SponsorshipRequest.COMPLETED, "paid": True}
    defaults.update(kwargs)
    return SponsorshipRequest.objects.create(name=name, **defaults)


def published_names(client, index):
    html = client.get(index.url).content.decode()
    return html


class TestPublishing:
    def test_completed_paid_event_is_shown(self, client, events_index):
        make(events_index, "PyCon Africa")
        assert "PyCon Africa" in published_names(client, events_index)

    def test_requested_event_is_hidden(self, client, events_index):
        make(events_index, "Pending Conf", status=SponsorshipRequest.REQUESTED)
        assert "Pending Conf" not in published_names(client, events_index)

    def test_approved_but_not_completed_is_hidden(self, client, events_index):
        make(events_index, "Upcoming Conf", status=SponsorshipRequest.APPROVED)
        assert "Upcoming Conf" not in published_names(client, events_index)

    def test_cancelled_event_is_hidden(self, client, events_index):
        make(events_index, "Cancelled Conf", status=SponsorshipRequest.CANCELLED)
        assert "Cancelled Conf" not in published_names(client, events_index)

    def test_completed_unpaid_event_is_shown_with_badge(self, client, events_index):
        make(events_index, "Community Meetup", paid=False)
        html = published_names(client, events_index)
        assert "Community Meetup" in html
        assert "badge-community" in html

    def test_paid_event_has_no_badge(self, client, events_index):
        make(events_index, "PyOhio", paid=True)
        html = published_names(client, events_index)
        assert "PyOhio" in html
        # The only badge on the page would be a community one.
        assert "badge-community" not in html


class TestModel:
    def test_is_published_requires_completed(self, events_index):
        assert make(events_index, "A", status=SponsorshipRequest.COMPLETED).is_published
        assert not make(events_index, "B", status=SponsorshipRequest.APPROVED).is_published

    def test_completed_unpaid_still_publishes(self, events_index):
        assert make(events_index, "C", status=SponsorshipRequest.COMPLETED, paid=False).is_published

    def test_amount_and_notes_never_reach_the_page(self, client, events_index):
        make(events_index, "Funded Conf", amount_requested="1234.56", notes="secret internal note")
        html = published_names(client, events_index)
        assert "Funded Conf" in html  # the event itself is shown
        assert "1234.56" not in html  # but its internal amount is not
        assert "secret internal note" not in html
