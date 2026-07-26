"""Sponsorship requests: the ORM record of community events Black Python Devs
is asked to support, and the ones it ends up supporting.

These are plain records, not Wagtail pages. Each moves through a lifecycle —
requested, approved, then completed once the event has happened. Only completed
requests surface on the public /events/ page; everything else stays internal.
CRUD is done through the Django admin and the Executor-only front-end (see the
data migration that provisions the "Executor" group).

The request form captures what a requester knows — event, dates, country, the
amount requested. `year` and `region` are derived on save (from `start_date` and
`country`) so the public events page can keep grouping by year then region
without anyone typing those by hand.
"""

from django.db import models
from django_countries.fields import CountryField

from .regions import region_for_country


class SponsorshipRequest(models.Model):
    """A request for Black Python Devs to sponsor a community event."""

    REQUESTED = "requested"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (REQUESTED, "Requested"),
        (APPROVED, "Approved"),
        (COMPLETED, "Completed"),
        (CANCELLED, "Cancelled"),
    ]

    name = models.CharField(max_length=200)
    url = models.URLField(blank=True, help_text="The event's website.")
    prospectus_url = models.URLField(blank=True, help_text="Link to the event's sponsorship prospectus.")

    start_date = models.DateField(
        null=True,
        help_text="Event start date. The year shown on the public site is taken from this.",
    )
    country = CountryField(
        help_text="Event country. The public listing groups by the country's region.",
    )

    # Derived on save() from start_date / country; not edited directly.
    year = models.PositiveIntegerField(db_index=True, editable=False)
    region = models.CharField(max_length=80, blank=True, editable=False)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=REQUESTED,
        db_index=True,
        help_text="Only completed sponsorships appear on the public events page.",
    )
    # Unpaid entries still publish; they render with a "community" badge.
    paid = models.BooleanField(
        default=True,
        help_text=(
            "Tick when Black Python Devs transferred funds. Leave unticked for community "
            "sponsorships contributed as visibility, volunteer time, or other non-monetary support."
        ),
    )
    amount_requested = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount the event asked for, for internal records. Never shown on the public site.",
    )
    notes = models.TextField(blank=True, help_text="Internal notes. Not shown publicly.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "sponsorship request"
        verbose_name_plural = "sponsorship requests"
        ordering = ["-year", "region", "name"]

    def save(self, *args, **kwargs):
        # Keep the derived fields in step with their sources. Only overwrite
        # when a source is present so legacy rows (year/region imported without
        # a start_date or country) keep the values they already carry.
        if self.start_date:
            self.year = self.start_date.year
        if self.country:
            self.region = region_for_country(self.country.code) or self.region
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.year})"

    @property
    def is_published(self):
        """Whether this belongs on the public events page.

        Completed is the gate; `paid` only decides whether the entry carries a
        "community" badge, so non-monetary support stays visible.
        """
        return self.status == self.COMPLETED
