"""Page types for the main site sections."""

from django.conf import settings
from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page
from wagtail.search import index

from core.blocks import BodyStreamBlock


class SEOMixin(models.Model):
    """Shared social-card fields, since every page wants them."""

    social_image = models.ForeignKey(
        "core.CustomImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    promote_panels = [
        MultiFieldPanel(Page.promote_panels, "Common page configuration"),
        FieldPanel("social_image"),
    ]

    class Meta:
        abstract = True


class HomePage(SEOMixin, Page):
    """The landing page: hero, principles grid, sponsors, latest posts."""

    hero_heading = models.CharField(
        max_length=255,
        default="Helping build communities for Black Pythonistas around the world.",
    )
    hero_image = models.ForeignKey(
        "core.CustomImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)
    show_sponsors = models.BooleanField(default=True)
    show_latest_posts = models.BooleanField(default=True)
    latest_posts_heading = models.CharField(max_length=120, default="Recently on the blog")

    content_panels = Page.content_panels + [
        MultiFieldPanel([FieldPanel("hero_heading"), FieldPanel("hero_image")], heading="Hero"),
        FieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("show_latest_posts"), FieldPanel("latest_posts_heading"), FieldPanel("show_sponsors")],
            heading="Sections",
        ),
    ]

    # Only one home page, and it sits at the site root.
    max_count = 1
    parent_page_types = ["wagtailcore.Page"]

    def get_context(self, request, *args, **kwargs):
        from blog.models import BlogPage
        from core.models import Sponsor

        context = super().get_context(request, *args, **kwargs)
        context["latest_posts"] = BlogPage.objects.live().public().order_by("-date")[:3]
        context["sponsors"] = Sponsor.objects.filter(active=True)
        return context


class StandardPage(SEOMixin, Page):
    """A generic content page: Code of Conduct, sponsorships, ambassadors."""

    introduction = models.TextField(blank=True)
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)

    content_panels = Page.content_panels + [FieldPanel("introduction"), FieldPanel("body")]

    search_fields = Page.search_fields + [index.SearchField("introduction"), index.SearchField("body")]


class AboutPage(SEOMixin, Page):
    """About page: story, principles, presence map, and the leadership roster.

    Leadership comes from the `Leader` snippet rather than page fields, so the
    same roster can be reused elsewhere without duplicating it.
    """

    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)
    show_map = models.BooleanField(default=True, verbose_name="Show global presence map")
    map_heading = models.CharField(max_length=120, blank=True, default="Our Global Presence")
    map_description = models.TextField(
        blank=True,
        default="This map shows the countries where Black Python Devs has community activity, events, or support.",
    )
    community_heading = models.CharField(max_length=120, blank=True, default="Join the Community")
    community_body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("show_map"), FieldPanel("map_heading"), FieldPanel("map_description")],
            heading="Presence map",
        ),
        MultiFieldPanel(
            [FieldPanel("community_heading"), FieldPanel("community_body")],
            heading="Join the community",
        ),
    ]

    max_count = 1

    def get_context(self, request, *args, **kwargs):
        from core.models import Leader

        context = super().get_context(request, *args, **kwargs)
        leaders = Leader.objects.all()
        context["executors"] = leaders.filter(role=Leader.EXECUTOR)
        context["team_leads"] = leaders.filter(role=Leader.TEAM_LEAD)
        context["advisors"] = leaders.filter(role=Leader.ADVISOR)
        context["council"] = leaders.filter(role=Leader.COUNCIL)
        return context


class MembershipPage(SEOMixin, Page):
    """"Become a Member": the pitch, plus the passwordless signup form.

    The form posts to allauth's signup view, so validation and rate limiting
    stay in allauth's hands; this page owns the copy, which editors control.
    """

    introduction = models.TextField(
        blank=True,
        default=(
            "Black Python Devs is a global community of Black Pythonistas. "
            "Membership is free — join us and connect with developers around the world."
        ),
    )
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)
    benefits_heading = models.CharField(max_length=120, blank=True, default="What you get")
    form_heading = models.CharField(max_length=120, blank=True, default="Become a member")
    form_help_text = models.CharField(
        max_length=255,
        blank=True,
        default="Enter your email and we'll send you a sign-in code. No password needed.",
    )
    discord_heading = models.CharField(max_length=120, blank=True, default="Connect your Discord account")
    discord_body = RichTextField(
        blank=True,
        help_text="Explain what connecting Discord does — it grants the role that allows posting.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("introduction"),
        MultiFieldPanel([FieldPanel("benefits_heading"), FieldPanel("body")], heading="Benefits"),
        MultiFieldPanel([FieldPanel("form_heading"), FieldPanel("form_help_text")], heading="Signup form"),
        MultiFieldPanel([FieldPanel("discord_heading"), FieldPanel("discord_body")], heading="Discord"),
    ]

    max_count = 1

    def get_context(self, request, *args, **kwargs):
        from allauth.account import app_settings as account_settings
        from allauth.account.forms import SignupForm
        from allauth.utils import get_form_class

        context = super().get_context(request, *args, **kwargs)
        form_class = get_form_class(account_settings.FORMS, "signup", SignupForm)
        context["signup_form"] = form_class()
        context["discord_invite_url"] = settings.DISCORD_INVITE_URL
        return context


class SupportPage(SEOMixin, Page):
    """Donation page: CommitChange widget, partners, supporters, pitch deck."""

    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)
    show_donate_widget = models.BooleanField(default=True)
    commitchange_npo_id = models.CharField(max_length=20, blank=True, default="6464")
    donation_amounts = models.CharField(max_length=120, blank=True, default="15,25,50,100,250,500")
    show_partnerships = models.BooleanField(default=True)
    show_foundational_supporters = models.BooleanField(default=True)
    show_sponsors = models.BooleanField(default=True)
    pitch_deck_url = models.URLField(
        blank=True,
        help_text="Canva (or similar) embed URL for the sponsorship pitch deck.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("body"),
        MultiFieldPanel(
            [
                FieldPanel("show_donate_widget"),
                FieldPanel("commitchange_npo_id"),
                FieldPanel("donation_amounts"),
            ],
            heading="Donation widget",
        ),
        MultiFieldPanel(
            [
                FieldPanel("show_partnerships"),
                FieldPanel("show_foundational_supporters"),
                FieldPanel("show_sponsors"),
                FieldPanel("pitch_deck_url"),
            ],
            heading="Sections",
        ),
    ]

    max_count = 1

    def get_context(self, request, *args, **kwargs):
        from collections import defaultdict

        from core.models import FoundationalSupport, Partner, Sponsor

        context = super().get_context(request, *args, **kwargs)
        context["partners"] = Partner.objects.all()
        context["sponsors"] = Sponsor.objects.filter(active=True)

        # Anonymous and unconfirmed support is deliberately left off the page.
        by_year = defaultdict(list)
        support = FoundationalSupport.objects.filter(status=FoundationalSupport.LISTED).select_related("user")
        for entry in support:
            by_year[entry.year].append(entry.display_name)
        # Newest year first; the template opens the current year by default.
        context["supporters_by_year"] = [(year, sorted(names)) for year, names in sorted(by_year.items(), reverse=True)]
        return context
