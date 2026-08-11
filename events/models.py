"""Events: BPD-organised events, plus the public listing of sponsored community events.

The sponsored-events records themselves now live in the ``sponsorships`` app as
standalone ``SponsorshipRequest`` rows managed from the Django admin; this page
only reads the completed ones for public display.
"""

from urllib.parse import parse_qs, urlparse

from django.db import models
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Orderable, Page
from wagtail.search import index

from core.blocks import BodyStreamBlock
from home.models import SEOMixin


def youtube_embed_url(url):
    """Turn any YouTube link an editor might paste into an embeddable one.

    Editors copy whatever the browser or the share sheet gives them — a full
    ``watch?v=`` URL, a ``youtu.be`` short link, or occasionally an ``/embed/``
    one already. All three become ``https://www.youtube.com/embed/<id>``.
    Anything unrecognised returns "" so the template can skip it rather than
    render a broken iframe.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/live/", "/shorts/")):
            video_id = parsed.path.split("/")[2]
    if not video_id:
        return ""
    return f"https://www.youtube.com/embed/{video_id}"


class EventIndexPage(SEOMixin, Page):
    """The /events/ page: supported-events explainer, BPD events, meetups."""

    introduction = models.TextField(
        blank=True,
        default=(
            "Black Python Devs aims to partner with Python conferences and events around the "
            "world to increase the visibility and opportunities for Black developers and leaders "
            "in the Python community."
        ),
    )
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)
    meetups_heading = models.CharField(max_length=120, blank=True, default="Regular Meetups")
    meetups_body = models.TextField(blank=True)
    grants_note = models.TextField(
        blank=True,
        help_text="Closing note about the grant criteria and how to get in touch.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("introduction"),
        FieldPanel("body"),
        MultiFieldPanel([FieldPanel("meetups_heading"), FieldPanel("meetups_body")], heading="Meetups"),
        FieldPanel("grants_note"),
    ]

    # Wagtail matches subpage_types exactly, so the EventPage subclass has to be
    # listed alongside it rather than being covered by it.
    subpage_types = ["events.EventPage", "events.LeadershipSummitPage"]
    max_count = 1

    def get_context(self, request, *args, **kwargs):
        from collections import defaultdict

        from sponsorships.models import SponsorshipRequest

        context = super().get_context(request, *args, **kwargs)
        context["bpd_events"] = EventPage.objects.child_of(self).live().public().order_by("-start_date")

        # Group completed sponsorships year → region → [entry], newest first.
        # Requested, approved, and cancelled support stays internal to the admin.
        grouped = defaultdict(lambda: defaultdict(list))
        completed = SponsorshipRequest.objects.filter(status=SponsorshipRequest.COMPLETED)
        for entry in completed.order_by("name"):
            grouped[entry.year][entry.region].append(entry)
        context["sponsored_by_year"] = [
            (year, sorted(regions.items())) for year, regions in sorted(grouped.items(), reverse=True)
        ]
        return context


class EventPage(SEOMixin, Page):
    """A Black Python Devs organised event, e.g. the Leadership Summit."""

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    banner = models.ForeignKey("core.CustomImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)

    prospectus_url = models.URLField(blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("start_date"), FieldPanel("end_date"), FieldPanel("location")],
            heading="When and where",
        ),
        FieldPanel("description"),
        FieldPanel("banner"),
        FieldPanel("body"),
        InlinePanel("sponsors", label="Event sponsors"),
        FieldPanel("prospectus_url"),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("description"),
        index.SearchField("body"),
        index.FilterField("start_date"),
    ]

    parent_page_types = ["events.EventIndexPage"]

    @property
    def is_upcoming(self):
        from django.utils import timezone

        return bool(self.start_date and self.start_date >= timezone.localdate())


class LeadershipSummitPage(EventPage):
    """A Leadership Summit, generated from its details rather than hand-written.

    Every summit says the same things in the same order — what it is, when and
    where, who's invited, and how to speak at or sponsor it — so this page type
    asks an editor for the details and the template writes the prose. Creating
    next year's summit is filling in a form, not copying last year's body.

    It subclasses `EventPage` to inherit the dates, venue, banner, and sponsors,
    so a summit still behaves like any other BPD event on the /events/ listing.
    `body` is still there for anything the generated sections don't cover — it
    renders after them.
    """

    TAGLINE = (
        "The Black Python Devs Leadership Summit is a single day workshop where leaders in the "
        "Python Community are invited to connect, grow, and learn with one another."
    )
    WHO_IS_INVITED = (
        "Anyone in leadership or wanting to get into leadership at the local, regional, or "
        "global level of the Python community."
    )

    city = models.CharField(
        max_length=120,
        blank=True,
        help_text='City and region, e.g. "Austin, TX". Used in the summary line.',
    )

    # The conference the summit is co-located with. Its own dates are kept
    # separately because the summit is usually one day inside a longer event.
    host_event_name = models.CharField(
        max_length=160,
        blank=True,
        help_text='The conference this summit runs alongside, e.g. "PyTexas". Leave blank if standalone.',
    )
    host_event_url = models.URLField(blank=True)
    host_event_start = models.DateField(null=True, blank=True, help_text="First day of the host conference.")
    host_event_end = models.DateField(null=True, blank=True, help_text="Last day of the host conference.")

    registration_url = models.URLField(
        blank=True,
        help_text="Leave blank until registration opens — the page then says announcements are coming.",
    )
    cfp_url = models.URLField(
        blank=True,
        verbose_name="Call for speakers URL",
        help_text="Leave blank until the call for speakers opens.",
    )
    cfp_deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name="Call for speakers closes",
        help_text="After this date the call is shown as closed rather than open.",
    )

    # Summits split into a morning and an afternoon session, and each is
    # recorded separately. Stored as whatever YouTube URL the editor pastes;
    # `youtube_embed_url` normalises it at render time.
    morning_video_url = models.URLField(
        blank=True,
        verbose_name="Morning session recording",
        help_text="YouTube link to the morning session. Leave blank until it's published.",
    )
    afternoon_video_url = models.URLField(
        blank=True,
        verbose_name="Afternoon session recording",
        help_text="YouTube link to the afternoon session. Leave blank until it's published.",
    )

    code_of_conduct_url = models.CharField(
        max_length=255,
        blank=True,
        default="/code-of-conduct/",
        help_text="The Black Python Devs Code of Conduct.",
    )
    host_code_of_conduct_url = models.URLField(
        blank=True,
        help_text="The host conference's Code of Conduct, if there is one.",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            # A summit is a single day, so `end_date` is kept off the form and
            # mirrored from `start_date` on save (see below).
            [FieldPanel("start_date", heading="Date"), FieldPanel("location"), FieldPanel("city")],
            heading="When and where",
        ),
        MultiFieldPanel(
            [
                FieldPanel("host_event_name"),
                FieldPanel("host_event_url"),
                FieldPanel("host_event_start"),
                FieldPanel("host_event_end"),
            ],
            heading="Host conference",
        ),
        FieldPanel("description"),
        FieldPanel("banner"),
        MultiFieldPanel(
            # The invitation wording itself is fixed — see `invitation` below.
            [FieldPanel("code_of_conduct_url"), FieldPanel("host_code_of_conduct_url")],
            heading="Codes of Conduct",
        ),
        MultiFieldPanel(
            [
                FieldPanel("registration_url"),
                FieldPanel("cfp_url"),
                FieldPanel("cfp_deadline"),
                FieldPanel("prospectus_url"),
            ],
            heading="Registration, speaking, and sponsorship",
        ),
        MultiFieldPanel(
            [FieldPanel("morning_video_url"), FieldPanel("afternoon_video_url")],
            heading="Recordings",
        ),
        FieldPanel("body", heading="Extra sections (optional)"),
        InlinePanel("sponsors", label="Event sponsors"),
    ]

    parent_page_types = ["events.EventIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "leadership summit"

    def save(self, *args, **kwargs):
        # A summit runs for one day. `start_date`/`end_date` are inherited from
        # EventPage and are what the /events/ listing sorts and renders on, so
        # rather than adding a separate field the end is mirrored from the start
        # — one date to fill in, and no half-set date range in the database.
        self.end_date = self.start_date
        super().save(*args, **kwargs)

    @property
    def date(self):
        """The single day the summit runs on."""
        return self.start_date

    @property
    def has_happened(self):
        """Whether this summit is in the past.

        A date that has passed says so outright. Published recordings say so
        too, and are checked because summits carried over from the static site
        never recorded a date — the 2024 page states only the year. Without
        this, a past summit with no date would advertise itself as upcoming.
        """
        from django.utils import timezone

        if self.recordings:
            return True
        return bool(self.date and self.date < timezone.localdate())

    @property
    def cfp_open(self):
        """Whether talks can still be submitted."""
        from django.utils import timezone

        if not self.cfp_url or self.has_happened:
            return False
        return not (self.cfp_deadline and timezone.localdate() > self.cfp_deadline)

    @property
    def cfp_closed(self):
        """Whether the call ran and has since shut."""
        from django.utils import timezone

        if self.has_happened or not self.cfp_deadline:
            return False
        return timezone.localdate() > self.cfp_deadline

    @property
    def recordings(self):
        """The published session recordings, as (label, embed URL) pairs.

        Empty until at least one is set, which is what keeps the "Watch Online"
        section off a summit that hasn't happened yet.
        """
        pairs = [
            ("Morning session", youtube_embed_url(self.morning_video_url)),
            ("Afternoon session", youtube_embed_url(self.afternoon_video_url)),
        ]
        return [(label, embed) for label, embed in pairs if embed]

    @property
    def tagline(self):
        """What the summit is. Editors can override it per-year via `description`."""
        return self.description or self.TAGLINE

    @property
    def invitation(self):
        """Who the summit is for.

        Deliberately not editable per-summit: this is who Black Python Devs
        invites to every summit, and it should read identically on all of them.
        Change `WHO_IS_INVITED` to change it everywhere at once.
        """
        return self.WHO_IS_INVITED

    @property
    def host_event_dates(self):
        """The host conference's run, as a display string, or "" if unknown."""
        if not self.host_event_start:
            return ""
        start = self.host_event_start
        end = self.host_event_end
        if not end or end == start:
            return start.strftime("%B %-d, %Y")
        if (start.year, start.month) == (end.year, end.month):
            return f"{start.strftime('%B %-d')} – {end.strftime('%-d, %Y')}"
        if start.year == end.year:
            return f"{start.strftime('%B %-d')} – {end.strftime('%B %-d, %Y')}"
        return f"{start.strftime('%B %-d, %Y')} – {end.strftime('%B %-d, %Y')}"


class EventSponsor(Orderable):
    """A sponsor of one specific event, at a given tier."""

    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    TIER_CHOICES = [(GOLD, "Gold"), (SILVER, "Silver"), (BRONZE, "Bronze")]

    page = ParentalKey(EventPage, related_name="sponsors", on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=GOLD)
    url = models.URLField(blank=True)
    logo = models.ForeignKey("core.CustomImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    panels = [FieldPanel("name"), FieldPanel("tier"), FieldPanel("url"), FieldPanel("logo")]

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"
