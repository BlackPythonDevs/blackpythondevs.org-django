"""Shared models: custom image, site-wide settings, and reusable snippets.

Everything the old Jekyll/render-engine site kept in `_data/*.json` lives here as
editable snippets so the community can maintain it without a deploy.
"""

from django.db import models
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import RichTextField
from wagtail.images.models import AbstractImage, AbstractRendition, Image
from wagtail.models import Orderable
from wagtail.search import index
from wagtail.snippets.models import register_snippet


class CustomImage(AbstractImage):
    """Wagtail image with a caption, so credits survive template changes."""

    caption = models.CharField(max_length=255, blank=True)

    admin_form_fields = Image.admin_form_fields + ("caption",)


class CustomRendition(AbstractRendition):
    image = models.ForeignKey(CustomImage, on_delete=models.CASCADE, related_name="renditions")

    class Meta:
        unique_together = (("image", "filter_spec", "focal_point_key"),)


# ── Site settings ─────────────────────────────────────────────────────────


@register_setting
class NavigationSettings(BaseSiteSetting, ClusterableModel):
    """Main-nav items, replacing the hardcoded `navigation` list in app.py."""

    panels = [InlinePanel("menu_items", label="Menu items")]

    class Meta:
        verbose_name = "Navigation"


class NavigationItem(Orderable):
    setting = ParentalKey(NavigationSettings, related_name="menu_items", on_delete=models.CASCADE)
    text = models.CharField(max_length=60)
    url = models.CharField(max_length=255, help_text="Relative path (/about/) or full URL.")
    icon = models.CharField(
        max_length=60,
        blank=True,
        help_text="Iconoir class name, e.g. iconoir-journal-page",
    )

    panels = [FieldPanel("text"), FieldPanel("url"), FieldPanel("icon")]

    def __str__(self):
        return self.text


@register_setting
class ToastSettings(BaseSiteSetting):
    """The dismissable announcement banner on the home page."""

    enabled = models.BooleanField(default=False)
    label = models.CharField(max_length=100, blank=True, default="Black Python Devs")
    text = models.CharField(max_length=255, blank=True)
    url = models.CharField(max_length=255, blank=True)

    panels = [
        MultiFieldPanel(
            [FieldPanel("enabled"), FieldPanel("label"), FieldPanel("text"), FieldPanel("url")],
            heading="Announcement toast",
        )
    ]

    class Meta:
        verbose_name = "Announcement toast"


@register_setting
class SocialSettings(BaseSiteSetting):
    discord_url = models.URLField(blank=True, default="https://discord.gg/XUc3tFqCT3")
    linkedin_url = models.URLField(blank=True, default="https://www.linkedin.com/company/black-python-devs")
    linkedin_group_url = models.URLField(blank=True, default="https://www.linkedin.com/groups/14336241/")
    x_url = models.URLField(blank=True, default="https://x.com/blackpythondevs")
    instagram_url = models.URLField(blank=True, default="https://www.instagram.com/blackpythondevs/")
    github_url = models.URLField(blank=True, default="https://github.com/BlackPythonDevs")
    contact_email = models.EmailField(blank=True, default="contact@blackpythondevs.com")

    class Meta:
        verbose_name = "Social links"


@register_setting
class FooterSettings(BaseSiteSetting):
    about_text = models.TextField(
        blank=True,
        default=(
            "Black Python Devs is a US Non-Profit Organization under the fiscal hosting of the "
            "GNOME Foundation. The foundation aims to expand access to Python communities and "
            "resources to communities of Black Python Developers around the world."
        ),
    )

    class Meta:
        verbose_name = "Footer"


# ── Snippets ──────────────────────────────────────────────────────────────


@register_snippet
class Sponsor(models.Model):
    """Corporate sponsor logo shown in the sponsor strip."""

    name = models.CharField(max_length=120)
    url = models.URLField(blank=True)
    logo = models.ForeignKey(CustomImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    logo_static_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Fallback path under /static/ if no image has been uploaded, e.g. images/jetbrains.webp",
    )
    sort_order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("url"),
        FieldPanel("logo"),
        FieldPanel("logo_static_path"),
        FieldPanel("sort_order"),
        FieldPanel("active"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


@register_snippet
class Partner(models.Model):
    """Partnership offering a community discount (TalkPython, mathspp, …)."""

    name = models.CharField(max_length=160)
    url = models.URLField(blank=True)
    promo_code = models.CharField(max_length=60, blank=True)
    description = RichTextField(blank=True)
    logo = models.ForeignKey(CustomImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    logo_static_path = models.CharField(max_length=255, blank=True)
    sort_order = models.IntegerField(default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("url"),
        FieldPanel("promo_code"),
        FieldPanel("description"),
        FieldPanel("logo"),
        FieldPanel("logo_static_path"),
        FieldPanel("sort_order"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


@register_snippet
class Leader(models.Model):
    """A member of leadership: executor, team lead, advisor, or council member."""

    EXECUTOR = "executor"
    TEAM_LEAD = "lead"
    ADVISOR = "advisor"
    COUNCIL = "council"
    ROLE_CHOICES = [
        (EXECUTOR, "Executor"),
        (TEAM_LEAD, "Team Lead"),
        (ADVISOR, "Advisor"),
        (COUNCIL, "Leadership Council"),
    ]

    name = models.CharField(max_length=120)
    title = models.CharField(max_length=160, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=COUNCIL)
    photo = models.ForeignKey(CustomImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    photo_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="External or /static/ photo URL, used when no image is uploaded.",
    )
    sort_order = models.IntegerField(default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("title"),
        FieldPanel("role"),
        FieldPanel("photo"),
        FieldPanel("photo_url"),
        FieldPanel("sort_order"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


@register_snippet
class FoundationalSupporter(models.Model):
    """Individual donor giving at least $200 in a given year."""

    name = models.CharField(max_length=160)
    year = models.PositiveIntegerField(db_index=True)

    panels = [FieldPanel("name"), FieldPanel("year")]

    class Meta:
        ordering = ["-year", "name"]
        unique_together = [("name", "year")]

    def __str__(self):
        return f"{self.name} — {self.year}"


@register_snippet
class Author(index.Indexed, models.Model):
    """Blog post author with a bio, replacing `_data/authors.json`."""

    name = models.CharField(max_length=160, unique=True)
    bio = models.TextField(blank=True)
    bpd_role = models.CharField(max_length=160, blank=True)
    photo = models.ForeignKey(CustomImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    website = models.URLField(blank=True)
    mastodon = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    user = models.OneToOneField(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="author_profile",
        help_text="Link this author to a site account so they can be credited automatically.",
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("bio"),
        FieldPanel("bpd_role"),
        FieldPanel("photo"),
        FieldPanel("user"),
        MultiFieldPanel(
            [FieldPanel("website"), FieldPanel("mastodon"), FieldPanel("linkedin"), FieldPanel("youtube")],
            heading="Social",
        ),
    ]

    search_fields = [index.SearchField("name"), index.SearchField("bio")]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
