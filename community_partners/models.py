"""Community partners: communities Black Python Devs supports on a
semi-regular basis.

A community partner is a friendly, separate community we help grow — by
sponsoring their events, sharing their posts, and inviting them to Black
Python Devs events. This is deliberately *not* `communities.Community`:
that model is for external groups that partner *with* us and are managed by
their own community admins through the front-end console. A community
partner is recorded only to publish it on the public `/community-partners/`
page, so it has no console, no admin membership, and no permissions.

Storage mirrors `corporate_sponsorships.Sponsor`'s logo handling (an
uploaded Wagtail image or a static fallback path) but stays Wagtail-free per
the issue: only `logo_static_path` is offered, since the partner page is a
plain Django view and there is no Wagtail image chooser in its admin.

`PUBLIC_FIELDS` is the only surface the public page may render, and it
excludes `notes` (internal) — the view projects rows through
`get_public_data()` rather than passing model instances to the template, so a
future field can never leak by being added to the model.
"""

from django.db import models


class CommunityPartner(models.Model):
    """A community Black Python Devs supports on a semi-regular basis."""

    # The fields the public /community-partners/ page may render. Anything
    # not listed here (notably `notes`) is internal-only.
    PUBLIC_FIELDS = (
        "id",
        "name",
        "description",
        "website",
        "logo_static_path",
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    logo_static_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Path under /static/ for this partner's logo, e.g. images/example.webp",
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Lower numbers appear first on the public page.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Show this partner on the public page.",
    )

    notes = models.TextField(blank=True, help_text="Internal notes. Never shown on the public site.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "community partner"
        verbose_name_plural = "community partners"

    def __str__(self):
        return self.name

    def get_public_data(self):
        """Return only the allowlisted, render-safe public values."""
        return {field: getattr(self, field) for field in self.PUBLIC_FIELDS}
