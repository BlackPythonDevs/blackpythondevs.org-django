"""Corporate sponsors: the companies whose money comes *in* to Black Python Devs.

Split out of core (issue #201). The table keeps its old name, core_sponsor.
"""

from dateutil.relativedelta import relativedelta
from django.db import models

from core.models import CustomImage


class Sponsor(models.Model):
    """Corporate sponsor logo shown in the sponsor strip.

    The `active` flag is the public "show in the sponsor strip" toggle,
    unchanged in meaning since before the lifecycle fields below existed.
    `status` tracks the internal contract lifecycle instead, and is what
    the auto-expiration job drives.

    Managed from its own neapolitan console
    (corporate_sponsorships.views.SponsorView, at /corporate-sponsors/) rather than Wagtail admin — this used to be a
    `@register_snippet` model with `panels`, but that console replaces the
    Wagtail snippet editor as the place to manage sponsors, and embeds the
    corporate-sponsorship checklist (see checklists/registry.py) that the
    Wagtail snippet form had no natural place for. `CustomBlogPage.sponsor`
    (blog/models.py) still points at this model via a plain FieldPanel; that
    just renders as an ordinary select in the page editor now instead of a
    snippet chooser.
    """

    STATUS_ACTIVE = "active"
    STATUS_EXPIRING_SOON = "expiring_soon"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRING_SOON, "Expiring soon"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

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

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    invoice_paid_date = models.DateField(
        null=True,
        blank=True,
        help_text="When Black Python Devs received payment. The sponsorship term runs one year from this date.",
    )
    # Derived on save() from invoice_paid_date; not edited directly.
    expires_at = models.DateField(null=True, blank=True, editable=False)
    contract_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Contract value, for internal records. Never shown on the public site.",
    )
    primary_contact_name = models.CharField(max_length=200, blank=True)
    primary_contact_email = models.EmailField(blank=True)
    # Derived from primary_contact_email on save(); not edited directly
    # (issue #144). The POC usually isn't a member when the contract starts,
    # but if the email matches one, the sponsor links to that account so
    # reminders and updates have a community record to reach.
    primary_contact_user = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sponsored_for",
        help_text="The member matching the primary contact email, if they have an account.",
    )

    class Meta:
        # Moved here from core (issue #201) without renaming the table, so
        # the move needed no data migration — only a state change.
        db_table = "core_sponsor"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        previous_invoice_paid_date = None
        if self.pk:
            previous_invoice_paid_date = (
                Sponsor.objects.filter(pk=self.pk).values_list("invoice_paid_date", flat=True).first()
            )

        # Keep expires_at in step with its source. Only overwrite when
        # invoice_paid_date is present so rows without one keep whatever
        # they already have.
        if self.invoice_paid_date:
            self.expires_at = self.invoice_paid_date + relativedelta(years=1)

        # Link the primary contact to their member account when one exists
        # (issue #144) — the same email lookup allauth uses. Runs on every
        # save so the console, admin, and imports all stay in step; a cleared
        # email clears the link.
        if self.primary_contact_email:
            from django.contrib.auth import get_user_model

            self.primary_contact_user = (
                get_user_model().objects.filter(email__iexact=self.primary_contact_email).first()
            )
        else:
            self.primary_contact_user = None

        super().save(*args, **kwargs)

        # Imported lazily: blog imports core.blocks, so importing blog at
        # module load time here would be circular.
        if self.invoice_paid_date and self.invoice_paid_date != previous_invoice_paid_date:
            from blog.sponsors import draft_sponsor_announcement

            draft_sponsor_announcement(self)
