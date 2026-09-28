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

    class Meta(AbstractImage.Meta):
        # Wagtail's own Image declares this; a custom model has to as well, or
        # non-superusers can never open the image chooser (its check is
        # `choose_<model_name>`).
        permissions = [("choose_customimage", "Can choose image")]


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


# Membership groups for the leadership roster. Like the "Ambassadors" group
# these carry no permissions of their own — they record who someone is, so
# views and templates can gate on membership and permissions can be attached
# later without a rename. A data migration provisions them.
#
# LEADERSHIP_GROUP_NAME is retired: it never carried any distinction from
# Leadership Council, so migration 0009 folded its members into Council and
# deleted it. The constant stays only because migrations 0003 and 0008
# import it by name and migrations are not rewritten after the fact.
COUNCIL_GROUP_NAME = "Leadership Council"
LEADERSHIP_GROUP_NAME = "Leadership"
EXECUTOR_GROUP_NAME = "Executor"

# Marks a member as a current student, so student-only features (like the
# ambassador programme CTA) can gate on it. Granted by leadership in the
# admin, the same way Council/Executor membership is.
STUDENT_GROUP_NAME = "Student"


def is_council_member(user):
    """Whether `user` is a member of the Leadership Council.

    Superusers pass so a site admin is never locked out of their own console.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=COUNCIL_GROUP_NAME).exists()


def is_leadership_or_above(user):
    """Whether `user` is on the Leadership Council or Executor (i.e.
    "leadership and above"). Mirrors `nominations.models.can_nominate`'s group
    check, which gates the same tier for a different feature.

    Superusers pass so a site admin is never locked out of their own console.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=(COUNCIL_GROUP_NAME, EXECUTOR_GROUP_NAME)).exists()


def is_student(user):
    """Whether `user` is in the Student group.

    Superusers pass so a site admin is never locked out of their own console.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=STUDENT_GROUP_NAME).exists()


@register_snippet
class Leader(models.Model):
    """A member of leadership: executor, team lead, advisor, or council member.

    This is the public roster shown on the About page and is deliberately not
    tied to a `User` — plenty of leaders predate having an account here. The
    matching auth groups above are maintained separately. `user` links the
    roster entry to a site account for council members who complete the
    onboarding photo/affiliations step themselves.
    """

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
    affiliations = models.CharField(
        max_length=255,
        blank=True,
        help_text="Other organizations or communities you're affiliated with.",
    )
    user = models.OneToOneField(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leader_profile",
        help_text="Link this roster entry to a site account.",
    )
    sort_order = models.IntegerField(default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("title"),
        FieldPanel("role"),
        FieldPanel("photo"),
        FieldPanel("photo_url"),
        FieldPanel("affiliations"),
        FieldPanel("user"),
        FieldPanel("sort_order"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


class FoundationalSupport(models.Model):
    """One person's foundational support ($200+) in one year.

    Support hangs off a user account rather than a bare name, so someone who
    gives across several years is one identity with a history. Imported
    supporters have placeholder accounts (see `core.supporters`) until they
    claim them.
    """

    LISTED = "listed"
    ANONYMOUS = "anonymous"
    PENDING = "pending"
    STATUS_CHOICES = [
        (LISTED, "Listed publicly"),
        (ANONYMOUS, "Anonymous"),
        (PENDING, "Pending confirmation"),
    ]

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="foundational_support",
    )
    year = models.PositiveIntegerField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=LISTED,
        help_text="Only 'Listed publicly' appears on the support page.",
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-year", "user__display_name"]
        unique_together = [("user", "year")]
        verbose_name = "foundational support"
        verbose_name_plural = "foundational support"

    def __str__(self):
        return f"{self.user} — {self.year} ({self.get_status_display()})"

    @property
    def display_name(self):
        return self.user.display_name or str(self.user)


@register_snippet
class Speaker(index.Indexed, models.Model):
    """Someone who has spoken at a Black Python Devs event.

    A snippet rather than a field on the event, because speakers come back:
    a keynote one year is a panellist the next, and their bio should be written
    once. Events reference this and add the year-specific part (their talk
    title) alongside — see `events.SummitSpeaker`.
    """

    name = models.CharField(max_length=160)
    url = models.URLField(blank=True, help_text="Their site, LinkedIn, or Mastodon.")
    photo = models.ForeignKey(CustomImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    photo_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="External or /static/ photo URL, used when no image is uploaded.",
    )
    bio = RichTextField(blank=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("url"),
        FieldPanel("photo"),
        FieldPanel("photo_url"),
        FieldPanel("bio"),
    ]

    search_fields = [index.SearchField("name"), index.SearchField("bio"), index.AutocompleteField("name")]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


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
