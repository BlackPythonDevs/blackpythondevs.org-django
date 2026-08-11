"""Events: sponsored-event publishing rules, and the generated summit page type."""

import datetime

import pytest
from django.core.management import call_command

from events.models import EventIndexPage, LeadershipSummitPage
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


SUMMIT_SLUG = "black-python-devs-leadership-summit-2027-at-pytexas"


class TestSummit2027:
    """The 2027 PyTexas summit is seeded as a LeadershipSummitPage, not a stub."""

    @pytest.fixture
    def summit(self, events_index):
        return LeadershipSummitPage.objects.get(slug=SUMMIT_SLUG)

    def test_page_carries_its_details(self, summit):
        assert summit.date == datetime.date(2027, 4, 16)
        assert summit.location == "Austin Central Library"
        assert summit.city == "Austin, TX"
        assert summit.host_event_name == "PyTexas"

    def test_page_generates_the_standard_sections(self, client, summit):
        # Only the time-invariant sections are asserted here — the seed carries a
        # fixed date, so the forward-looking copy is covered by the relative-date
        # tests below rather than by assertions that expire in April 2027.
        html = client.get(summit.url).content.decode()
        assert "single day workshop" in html
        assert "Who is Invited?" in html

    def test_page_states_when_and_where(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "16 April 2027" in html
        assert "Austin, TX" in html
        assert "PyTexas" in html
        # The host conference's own longer run, generated from its dates.
        assert "April 16 – 18, 2027" in html

    def test_summit_is_listed_on_the_events_page(self, client, events_index):
        html = client.get(events_index.url).content.decode()
        assert "Leadership Summit 2027 at PyTexas" in html

    def test_reseeding_does_not_duplicate_the_page(self, events_index):
        call_command("bootstrap_site", verbosity=0)
        assert LeadershipSummitPage.objects.filter(slug=SUMMIT_SLUG).count() == 1


class TestSummitTemplate:
    """A blank summit still produces a complete page — that's the point."""

    @pytest.fixture
    def summit(self, events_index):
        from django.utils import timezone

        # Relative, not a hardcoded year: these assertions are about the
        # forward-looking copy, which a fixed date would silently stop
        # exercising once that date went past.
        page = LeadershipSummitPage(
            title="Leadership Summit",
            slug="leadership-summit-upcoming",
            start_date=timezone.localdate() + datetime.timedelta(days=365),
        )
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    def test_standard_wording_is_used_when_fields_are_blank(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "single day workshop" in html
        assert "Anyone in leadership or wanting to get into leadership" in html
        assert "Black Python Devs Code of Conduct" in html

    def test_editors_can_override_the_tagline(self, client, summit):
        summit.description = "A different pitch for this year."
        summit.save_revision().publish()

        html = client.get(summit.url).content.decode()
        assert "A different pitch for this year." in html
        assert "single day workshop" not in html

    def test_the_invitation_wording_is_not_editable(self, client, summit):
        """Every summit invites the same people, in the same words."""
        assert summit.invitation == LeadershipSummitPage.WHO_IS_INVITED
        # No per-summit field to diverge from it.
        assert not hasattr(summit, "who_is_invited")

        # Even with a custom tagline, the invitation is unchanged.
        summit.description = "A different pitch for this year."
        summit.save_revision().publish()
        html = client.get(summit.url).content.decode()
        assert LeadershipSummitPage.WHO_IS_INVITED in html

    def test_calls_are_announced_as_pending_until_their_links_exist(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "Registration, speakers, and the schedule will be announced" in html
        assert "The call for speakers will be released closer to the event." in html
        assert "Sponsor information will be released closer to the event." in html

    def test_links_replace_the_pending_wording_once_set(self, client, summit):
        summit.registration_url = "https://example.com/register"
        summit.cfp_url = "https://example.com/cfp"
        summit.prospectus_url = "https://example.com/prospectus"
        summit.save_revision().publish()

        html = client.get(summit.url).content.decode()
        assert "https://example.com/register" in html
        assert "Submit a talk" in html
        assert "Read the sponsorship prospectus" in html
        assert "will be released closer to the event" not in html

    def test_extra_body_blocks_render_after_the_generated_sections(self, client, summit):
        summit.body = [("heading", "Travel grants")]
        summit.save_revision().publish()

        html = client.get(summit.url).content.decode()
        assert html.index("Speaking and Sponsorship") < html.index("Travel grants")

    def test_host_conference_sections_are_skipped_when_standalone(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "We're partnering with" not in html


class TestHostEventDates:
    """The host conference's run is written out from its two dates."""

    def make(self, start, end):
        return LeadershipSummitPage(host_event_start=start, host_event_end=end).host_event_dates

    def test_blank_without_a_start_date(self):
        assert self.make(None, None) == ""

    def test_single_day(self):
        assert self.make(datetime.date(2027, 4, 16), None) == "April 16, 2027"

    def test_same_month(self):
        assert self.make(datetime.date(2027, 4, 16), datetime.date(2027, 4, 18)) == "April 16 – 18, 2027"

    def test_spanning_months(self):
        assert self.make(datetime.date(2027, 4, 30), datetime.date(2027, 5, 2)) == "April 30 – May 2, 2027"

    def test_spanning_years(self):
        assert (
            self.make(datetime.date(2027, 12, 30), datetime.date(2028, 1, 2)) == "December 30, 2027 – January 2, 2028"
        )


class TestSummitInWagtailAdmin:
    """The point of the page type is creating one in the CMS, so check it opens.

    `sponsors` is an InlinePanel whose ParentalKey targets EventPage, the parent
    in a multi-table inheritance pair — worth asserting the child's form builds.
    """

    @pytest.fixture
    def editor(self, db):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_superuser(username="cms", email="cms@example.com", password="pw")

    def test_create_form_renders(self, client, editor, events_index):
        client.force_login(editor)
        response = client.get(f"/cms/pages/add/events/leadershipsummitpage/{events_index.pk}/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "Host conference" in html
        assert "Event sponsors" in html
        # One day, one date field — no end date to fill in.
        assert 'name="end_date"' not in html

    def test_summit_is_offered_under_the_events_index(self, client, editor, events_index):
        client.force_login(editor)
        html = client.get(f"/cms/pages/{events_index.pk}/add_subpage/").content.decode()
        assert "Leadership summit" in html


class TestSummitIsOneDay:
    """Summits run for a single day, so there is one date to fill in."""

    @pytest.fixture
    def summit(self, events_index):
        page = LeadershipSummitPage(
            title="Leadership Summit 2029",
            slug="leadership-summit-2029",
            start_date=datetime.date(2029, 6, 3),
        )
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    def test_end_date_mirrors_the_single_date(self, summit):
        summit.refresh_from_db()
        assert summit.date == datetime.date(2029, 6, 3)
        # Mirrored so the inherited /events/ listing has a coherent record.
        assert summit.end_date == summit.start_date

    def test_a_stale_end_date_is_corrected_on_save(self, summit):
        summit.end_date = datetime.date(2029, 6, 30)
        summit.save()
        summit.refresh_from_db()
        assert summit.end_date == datetime.date(2029, 6, 3)

    def test_page_shows_one_date_not_a_range(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "3 June 2029" in html
        assert "3 June 2029 –" not in html


class TestConvertSummitsCommand:
    """Retyping an existing EventPage into a LeadershipSummitPage in place."""

    @pytest.fixture
    def legacy(self, events_index):
        from events.models import EventPage

        page = EventPage(
            title="Black Python Devs Leadership Summit 2024",
            slug="leadership-summit-2024",
            start_date=datetime.date(2024, 8, 2),
            end_date=datetime.date(2024, 8, 4),
            body=[("heading", "Watch Online")],
        )
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    def test_dry_run_changes_nothing(self, legacy):
        call_command("convert_summits", verbosity=0)
        assert not LeadershipSummitPage.objects.filter(pk=legacy.pk).exists()

    def test_apply_retypes_the_page_in_place(self, legacy):
        call_command("convert_summits", "--apply", verbosity=0)

        summit = LeadershipSummitPage.objects.get(pk=legacy.pk)
        # Same page: same id, slug, url, and body.
        assert summit.pk == legacy.pk
        assert summit.slug == legacy.slug
        assert summit.url == legacy.url
        assert summit.body[0].value == "Watch Online"
        # The stale end date is collapsed onto the single summit date.
        assert summit.end_date == summit.start_date == datetime.date(2024, 8, 2)

    def test_converted_page_uses_the_summit_template(self, client, legacy):
        call_command("convert_summits", "--apply", verbosity=0)
        html = client.get(legacy.url).content.decode()
        assert "Who is Invited?" in html
        assert "Watch Online" in html  # the existing body survives

    def test_conversion_is_idempotent(self, legacy):
        call_command("convert_summits", "--apply", verbosity=0)
        call_command("convert_summits", "--apply", verbosity=0)
        assert LeadershipSummitPage.objects.filter(pk=legacy.pk).count() == 1

    def test_named_slugs_limit_what_is_converted(self, events_index, legacy):
        from events.models import EventPage

        other = EventPage(title="Some Other Summit", slug="other-summit")
        events_index.add_child(instance=other)
        other.save_revision().publish()

        call_command("convert_summits", "leadership-summit-2024", "--apply", verbosity=0)
        assert LeadershipSummitPage.objects.filter(pk=legacy.pk).exists()
        assert not LeadershipSummitPage.objects.filter(pk=other.pk).exists()


class TestSpeakerAndScheduleBlocks:
    """Speakers and schedules are structured blocks, not hand-written HTML."""

    @pytest.fixture
    def summit(self, events_index):
        page = LeadershipSummitPage(
            title="Leadership Summit 2030",
            slug="leadership-summit-2030",
            start_date=datetime.date(2030, 9, 9),
            body=[
                (
                    "speakers",
                    {
                        "heading": "Keynote Speakers",
                        "intro": "<p>Two of them.</p>",
                        "speakers": [
                            {
                                "name": "Ada Speaker",
                                "url": "https://example.com/ada",
                                "talk_title": "On Leadership",
                                "photo": None,
                                "photo_url": "/static/images/ada.webp",
                                "bio": "<p>Ada builds things.</p>",
                            },
                            {
                                "name": "Grace Speaker",
                                "url": "",
                                "talk_title": "",
                                "photo": None,
                                "photo_url": "",
                                "bio": "",
                            },
                        ],
                    },
                ),
                (
                    "schedule",
                    {
                        "heading": "Schedule",
                        "intro": "",
                        "items": [
                            {"time": "09:00", "title": "Welcome", "presenter": ""},
                            {"time": "09:15", "title": "Keynote", "presenter": "Ada Speaker"},
                        ],
                    },
                ),
            ],
        )
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    def test_speakers_render_with_names_links_and_talks(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "Keynote Speakers" in html
        assert "Two of them." in html
        assert 'href="https://example.com/ada"' in html
        assert "On Leadership" in html
        assert "Ada builds things." in html

    def test_static_photo_url_is_used_when_no_image_is_uploaded(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert '<img class="speaker-photo" src="/static/images/ada.webp"' in html

    def test_a_speaker_with_only_a_name_still_renders(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert "Grace Speaker" in html

    def test_schedule_renders_as_a_table(self, client, summit):
        html = client.get(summit.url).content.decode()
        assert '<table role="grid" class="schedule">' in html
        # Wrapped so a wide schedule scrolls itself rather than the page.
        assert "<figure>" in html
        for heading in ("Time", "Session", "Presenter"):
            assert f'<th scope="col">{heading}</th>' in html
        # The time is the row header, not a plain cell.
        assert '<th scope="row">09:00</th>' in html
        assert "Welcome" in html
        assert "Ada Speaker" in html

    def test_presenter_column_is_dropped_when_nobody_is_named(self, client, events_index):
        from django.utils import timezone

        page = LeadershipSummitPage(
            title="Logistics Only",
            slug="logistics-only",
            start_date=timezone.localdate() + datetime.timedelta(days=30),
            body=[
                (
                    "schedule",
                    {
                        "heading": "Schedule",
                        "intro": "",
                        "items": [
                            {"time": "09:00", "title": "Doors open", "presenter": ""},
                            {"time": "17:00", "title": "Close", "presenter": ""},
                        ],
                    },
                )
            ],
        )
        events_index.add_child(instance=page)
        page.save_revision().publish()

        html = client.get(page.url).content.decode()
        assert '<th scope="col">Time</th>' in html
        # An empty column of em dashes is worse than no column.
        assert '<th scope="col">Presenter</th>' not in html

    def test_blocks_are_available_on_any_body_stream(self):
        from core.blocks import BodyStreamBlock

        names = BodyStreamBlock().child_blocks.keys()
        assert "speakers" in names
        assert "schedule" in names


class TestYouTubeEmbedUrl:
    """Editors paste whatever YouTube hands them; all of it has to embed."""

    def check(self, url):
        from events.models import youtube_embed_url

        return youtube_embed_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=p95Cuczqig8",
            "https://youtube.com/watch?v=p95Cuczqig8",
            "https://www.youtube.com/watch?v=p95Cuczqig8&t=42s",
            "https://youtu.be/p95Cuczqig8",
            "https://youtu.be/p95Cuczqig8?t=42",
            "https://www.youtube.com/embed/p95Cuczqig8",
            "https://www.youtube.com/live/p95Cuczqig8",
        ],
    )
    def test_recognised_links_become_embed_urls(self, url):
        assert self.check(url) == "https://www.youtube.com/embed/p95Cuczqig8"

    @pytest.mark.parametrize("url", ["", "https://example.com/video", "https://www.youtube.com/", "not a url"])
    def test_unrecognised_links_are_dropped(self, url):
        # "" rather than a broken iframe.
        assert self.check(url) == ""


class TestSummitRecordings:
    @pytest.fixture
    def summit(self, events_index):
        page = LeadershipSummitPage(
            title="Leadership Summit 2031",
            slug="leadership-summit-2031",
            start_date=datetime.date(2031, 3, 4),
        )
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    def test_no_watch_section_before_recordings_exist(self, client, summit):
        assert summit.recordings == []
        assert "Watch Online" not in client.get(summit.url).content.decode()

    def test_both_sessions_embed_once_set(self, client, summit):
        summit.morning_video_url = "https://www.youtube.com/watch?v=AAAAAAAAAAA"
        summit.afternoon_video_url = "https://youtu.be/BBBBBBBBBBB"
        summit.save_revision().publish()

        html = client.get(summit.url).content.decode()
        assert "Watch Online" in html
        assert "https://www.youtube.com/embed/AAAAAAAAAAA" in html
        assert "https://www.youtube.com/embed/BBBBBBBBBBB" in html
        assert "Morning session" in html
        assert "Afternoon session" in html

    def test_one_session_alone_still_renders(self, client, summit):
        summit.afternoon_video_url = "https://youtu.be/BBBBBBBBBBB"
        summit.save_revision().publish()

        html = client.get(summit.url).content.decode()
        assert "Afternoon session" in html
        assert "Morning session" not in html


class TestPastSummitsDropForwardLookingCopy:
    """A summit that has happened is a record, not a call to action."""

    def make(self, events_index, slug, **kwargs):
        page = LeadershipSummitPage(title=slug.title(), slug=slug, **kwargs)
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    @pytest.fixture
    def today(self):
        from django.utils import timezone

        return timezone.localdate()

    def test_a_dated_past_summit_has_happened(self, events_index, today):
        page = self.make(events_index, "past-summit", start_date=today - datetime.timedelta(days=1))
        assert page.has_happened

    def test_an_upcoming_summit_has_not(self, events_index, today):
        page = self.make(events_index, "future-summit", start_date=today + datetime.timedelta(days=1))
        assert not page.has_happened

    def test_recordings_mark_a_dateless_summit_as_past(self, events_index):
        """Summits carried over from the static site never recorded a date."""
        page = self.make(events_index, "old-summit", morning_video_url="https://youtu.be/AAAAAAAAAAA")
        assert page.date is None
        assert page.has_happened

    def test_a_dateless_summit_without_recordings_is_still_upcoming(self, events_index):
        page = self.make(events_index, "unscheduled-summit")
        assert not page.has_happened

    def test_past_summit_hides_coming_soon_and_pending_copy(self, client, events_index, today):
        page = self.make(
            events_index,
            "finished-summit",
            start_date=today - datetime.timedelta(days=30),
            registration_url="https://example.com/register",
        )
        html = client.get(page.url).content.decode()
        assert "Coming Soon" not in html
        assert "Register for the summit" not in html
        assert "will be announced on this page" not in html
        assert "will be released closer to the event" not in html
        # The support ask survives, in past tense.
        assert "support Black Python Devs" in html
        # And the parts that describe the summit itself remain.
        assert "Who is Invited?" in html

    def test_upcoming_summit_still_shows_coming_soon(self, client, events_index, today):
        page = self.make(events_index, "next-summit", start_date=today + datetime.timedelta(days=30))
        html = client.get(page.url).content.decode()
        assert "Coming Soon" in html
        assert "will be announced on this page" in html


class TestCallForSpeakersDeadline:
    def make(self, events_index, slug, **kwargs):
        page = LeadershipSummitPage(title=slug.title(), slug=slug, **kwargs)
        events_index.add_child(instance=page)
        page.save_revision().publish()
        return page

    @pytest.fixture
    def today(self):
        from django.utils import timezone

        return timezone.localdate()

    def test_open_while_before_the_deadline(self, client, events_index, today):
        page = self.make(
            events_index,
            "cfp-open",
            start_date=today + datetime.timedelta(days=60),
            cfp_url="https://example.com/cfp",
            cfp_deadline=today + datetime.timedelta(days=10),
        )
        assert page.cfp_open and not page.cfp_closed
        assert "Submit a talk" in client.get(page.url).content.decode()

    def test_closed_once_the_deadline_passes(self, client, events_index, today):
        page = self.make(
            events_index,
            "cfp-closed",
            start_date=today + datetime.timedelta(days=30),
            cfp_url="https://example.com/cfp",
            cfp_deadline=today - datetime.timedelta(days=1),
        )
        assert page.cfp_closed and not page.cfp_open
        html = client.get(page.url).content.decode()
        assert "The call for speakers has closed." in html
        assert "Submit a talk" not in html

    def test_no_deadline_means_open_for_as_long_as_the_link_is_up(self, events_index, today):
        page = self.make(
            events_index,
            "cfp-no-deadline",
            start_date=today + datetime.timedelta(days=30),
            cfp_url="https://example.com/cfp",
        )
        assert page.cfp_open

    def test_a_past_summit_is_neither_open_nor_closed(self, events_index, today):
        page = self.make(
            events_index,
            "cfp-past",
            start_date=today - datetime.timedelta(days=1),
            cfp_url="https://example.com/cfp",
            cfp_deadline=today - datetime.timedelta(days=30),
        )
        assert not page.cfp_open
        assert not page.cfp_closed
