"""Council nominations: who the current leadership puts forward for a seat on
the Black Python Devs Leadership Council.

Like the sponsorships and ambassadors apps these are plain records, not Wagtail
pages, and they move through a lifecycle — submitted, under review, then
accepted or declined. A nominator can withdraw their own nomination while it is
still open.

Nominating is restricted to the people already in leadership: members of the
"Leadership Council" and "Leadership" groups (see `core.models`). Those are
membership groups that deliberately carry no permissions, so the views gate on
group membership rather than on Django model permissions.

The nominee is stored as a name and email rather than a `User` FK, because
plenty of the people worth nominating have no account here yet. `nominee_user`
links the record to an account when there is one, so a nominee who is already a
member can be recognised.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME

# Membership in either group is what earns the right to nominate. Kept here so
# the views, templates, and tests share one source of truth.
NOMINATOR_GROUP_NAMES = (COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME)


def can_nominate(user):
    """Whether `user` may nominate someone for the council.

    Superusers pass so a site admin is never locked out of their own console.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=NOMINATOR_GROUP_NAMES).exists()


def current_term_year():
    """Default nomination cycle: the current calendar year."""
    return timezone.now().year


class CouncilNomination(models.Model):
    """One leader's nomination of one person for the Leadership Council."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "review"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    STATUS_CHOICES = [
        (SUBMITTED, "Submitted"),
        (UNDER_REVIEW, "Under review"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
        (WITHDRAWN, "Withdrawn"),
    ]

    # The statuses a nominator may still edit or withdraw their own record in.
    OPEN_STATUSES = (SUBMITTED, UNDER_REVIEW)

    nominator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="council_nominations",
        help_text="The leader who put this person forward.",
    )

    nominee_name = models.CharField(max_length=200, help_text="The nominee's full name.")
    nominee_email = models.EmailField(help_text="Best contact email for the nominee.")
    nominee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="council_nominations_received",
        help_text="Link the nomination to a site account, if the nominee already has one.",
    )
    nominee_url = models.URLField(
        blank=True,
        help_text="Optional link — GitHub, LinkedIn, or a personal site.",
    )

    statement = models.TextField(
        help_text="Why this person should serve on the Leadership Council.",
    )
    contributions = models.TextField(
        blank=True,
        help_text="Optional. What they've already contributed to Black Python Devs or the wider community.",
    )
    nominee_consulted = models.BooleanField(
        default=False,
        help_text="Tick if you've confirmed the nominee is willing to serve.",
    )

    term_year = models.PositiveIntegerField(
        default=current_term_year,
        db_index=True,
        help_text="The nomination cycle this belongs to.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=SUBMITTED,
        db_index=True,
    )
    notes = models.TextField(blank=True, help_text="Internal notes. Not shown to the nominee.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "council nomination"
        verbose_name_plural = "council nominations"
        ordering = ["-term_year", "nominee_name"]
        constraints = [
            # One nominator gets one nomination per person per cycle. Seconding
            # someone else's nomination is a separate record by a different
            # nominator, which is exactly how support is counted.
            models.UniqueConstraint(
                fields=["nominator", "nominee_email", "term_year"],
                name="unique_nomination_per_nominator_and_cycle",
            )
        ]

    def __str__(self):
        return f"{self.nominee_name} ({self.term_year})"

    @property
    def is_open(self):
        """Whether the nominator can still edit or withdraw this."""
        return self.status in self.OPEN_STATUSES

    def editable_by(self, user):
        """Only the nominator edits their own wording, and only while it's open.

        Status changes are a council decision made in the admin, not something a
        nominator does to their own record.
        """
        return self.is_open and (user.is_superuser or self.nominator_id == user.pk)
