"""Events: BPD-organised events, plus the public listing of sponsored community events.

The sponsored-events records themselves now live in the ``sponsorships`` app as
standalone ``SponsorshipRequest`` rows managed from the Django admin; this page
only reads the completed ones for public display.
"""

from django.db import models
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Orderable, Page
from wagtail.search import index

from core.blocks import BodyStreamBlock
from home.models import SEOMixin


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

    subpage_types = ["events.EventPage"]
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
    banner = models.ForeignKey(
        "core.CustomImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)

    tito_event = models.CharField(
        max_length=200,
        blank=True,
        help_text="Tito event slug, e.g. black-python-devs/leadership-summit",
    )
    prospectus_url = models.URLField(blank=True)
    commitchange_campaign_id = models.CharField(max_length=40, blank=True)
    commitchange_designation = models.CharField(max_length=200, blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("start_date"), FieldPanel("end_date"), FieldPanel("location")],
            heading="When and where",
        ),
        FieldPanel("description"),
        FieldPanel("banner"),
        FieldPanel("body"),
        InlinePanel("sponsors", label="Event sponsors"),
        MultiFieldPanel(
            [
                FieldPanel("tito_event"),
                FieldPanel("prospectus_url"),
                FieldPanel("commitchange_campaign_id"),
                FieldPanel("commitchange_designation"),
            ],
            heading="Tickets and fundraising",
        ),
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
    logo = models.ForeignKey(
        "core.CustomImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    panels = [FieldPanel("name"), FieldPanel("tier"), FieldPanel("url"), FieldPanel("logo")]

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"
