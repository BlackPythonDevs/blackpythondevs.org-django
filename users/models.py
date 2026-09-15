from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django_countries.fields import CountryField

from .regions import region_for_country


class User(AbstractUser):
    """Custom user, swapped in from day one so it can grow later.

    Email is the login identifier (see ACCOUNT_LOGIN_METHODS), but Wagtail's
    admin still expects a username, so both are kept.
    """

    MEMBER = "member"
    SUPPORTER = "supporter"
    MEMBER_TYPE_CHOICES = [
        (MEMBER, "BPD Member"),
        (SUPPORTER, "Friend / Supporter / Ally"),
    ]

    LATAM = "latam"
    INDIGENOUS = "indigenous"
    PACIFIC_ISLANDER = "pacific_islander"
    ASIAN_RELIGIOUS_MINORITY = "asian_religious_minority"
    SUBCOMMUNITY_CHOICES = [
        (LATAM, "LATAM"),
        (INDIGENOUS, "Native/Indigenous (including Maori, Aboriginal)"),
        (PACIFIC_ISLANDER, "Pacific Islander"),
        (ASIAN_RELIGIOUS_MINORITY, "Asian Religious Minority"),
    ]

    SPONSOR_EVENTS = "sponsor_events"
    PARTNER_ANNOUNCEMENTS = "partner_announcements"
    CONFERENCE_CFPS = "conference_cfps"
    VOLUNTEER_OPPORTUNITIES = "volunteer_opportunities"
    COMMUNICATION_PREFERENCE_CHOICES = [
        (SPONSOR_EVENTS, "Sponsor events & job opportunities"),
        (PARTNER_ANNOUNCEMENTS, "Community partner announcements and opportunities"),
        (CONFERENCE_CFPS, "Conferences/CFPs in your area"),
        (VOLUNTEER_OPPORTUNITIES, "BPD community volunteer opportunities"),
    ]

    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    pronouns = models.CharField(max_length=60, blank=True)
    bio = models.TextField(blank=True)

    member_type = models.CharField(max_length=20, choices=MEMBER_TYPE_CHOICES, blank=True)
    country = CountryField(blank=True, help_text="Where you currently reside. Used to match you to a region.")
    # Derived on save() from `country`; not edited directly.
    region = models.CharField(max_length=80, blank=True, editable=False)
    subcommunities = ArrayField(
        models.CharField(max_length=40, choices=SUBCOMMUNITY_CHOICES),
        blank=True,
        default=list,
        help_text="Subcommunities you identify with, so we can share opportunities relevant to you.",
    )
    communication_preferences = ArrayField(
        models.CharField(max_length=40, choices=COMMUNICATION_PREFERENCE_CHOICES),
        blank=True,
        default=list,
        help_text="What you'd like to hear about.",
    )
    onboarding_completed_at = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return self.display_name or self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if self.country:
            self.region = region_for_country(self.country.code) or self.region
        super().save(*args, **kwargs)

    @property
    def needs_onboarding(self):
        return self.onboarding_completed_at is None
