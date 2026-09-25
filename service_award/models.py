"""Community Service Award nominations: leadership puts forward community
members who've given outstanding service, for the annual award described at
https://github.com/BlackPythonDevs/blackpythondevs/blob/main/programs/distinguished-service-award.md

Like `nominations` (council seats) and `elections` (the Executorship) this
is a plain record, not a Wagtail page, and it moves through the same
lifecycle: submitted, under review, then accepted or declined. A nominator
can withdraw their own nomination while it's still open.

Nominating is restricted to leadership — the Leadership Council and Executor
groups (see `core.models.is_leadership_or_above`) — matching the programme
doc's "the leadership team manages nominations and voting" language. This is
deliberately broader than `nominations.can_nominate`, which only checks the
Council group: Executors run the award too.

The award excludes Executors and past recipients — Council members (who
aren't running the award day-to-day) remain eligible. Past winners are
tracked in `ServiceAwardRecipient` rather than as a nomination status, so
the exclusion survives even if the nomination that led to a win is later
edited or withdrawn, and so a recipient can be recorded without a nomination
ever having existed (e.g. backfilling past years).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import is_leadership_or_above


def can_nominate(user):
    """Whether `user` may nominate someone for the Community Service Award.

    Superusers pass so a site admin is never locked out of their own console.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return is_leadership_or_above(user)


def current_award_year():
    """Default award cycle: the current calendar year."""
    return timezone.now().year


class ServiceAwardNomination(models.Model):
    """One leader's nomination of one community member for the award."""

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
        related_name="service_award_nominations",
        help_text="The leader who put this person forward.",
    )

    nominee_name = models.CharField(max_length=200, help_text="The nominee's full name.")
    nominee_email = models.EmailField(help_text="Best contact email for the nominee.")
    nominee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_award_nominations_received",
        help_text="Link the nomination to a site account, if the nominee already has one.",
    )
    nominee_url = models.URLField(
        blank=True,
        help_text="Optional link — GitHub, LinkedIn, or a personal site.",
    )

    statement = models.TextField(
        help_text="Why this person deserves the Community Service Award.",
    )
    contributions = models.TextField(
        blank=True,
        help_text="Optional. What they've already contributed to Black Python Devs or the wider community.",
    )

    award_year = models.PositiveIntegerField(
        default=current_award_year,
        db_index=True,
        help_text="The award cycle this belongs to.",
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
        verbose_name = "service award nomination"
        verbose_name_plural = "service award nominations"
        ordering = ["-award_year", "nominee_name"]
        constraints = [
            # One nominator gets one nomination per person per cycle. Seconding
            # someone else's nomination is a separate record by a different
            # nominator, which is exactly how support is counted.
            models.UniqueConstraint(
                fields=["nominator", "nominee_email", "award_year"],
                name="unique_service_award_nomination_per_nominator_and_cycle",
            )
        ]

    def __str__(self):
        return f"{self.nominee_name} ({self.award_year})"

    @property
    def is_open(self):
        """Whether the nominator can still edit or withdraw this."""
        return self.status in self.OPEN_STATUSES

    def editable_by(self, user):
        """Only the nominator edits their own wording, and only while it's open.

        Status changes, and recording the eventual winner, are a leadership
        decision made in the admin, not something a nominator does themselves.
        """
        return self.is_open and (user.is_superuser or self.nominator_id == user.pk)

    def reinstatable_by(self, user):
        """Whether `user` can bring this withdrawn nomination straight back,
        as-is, without resubmitting the form (see `NominationReinstateView`).

        Only for the current cycle — a withdrawn nomination from a past year
        is history, not something to silently reopen — and only the
        nominator who withdrew it, or a superuser.
        """
        if self.status != self.WITHDRAWN:
            return False
        if self.award_year != current_award_year():
            return False
        return user.is_superuser or self.nominator_id == user.pk


def group_by_nominee(nominations):
    """Group nominations by nominee email (case-insensitively), the same way
    `nominations.CouncilNomination`'s docstring describes seconding: a second
    leader nominating the same person is separate support for one nominee,
    not a separate candidate. Leadership needs to see that combined support
    rather than one indistinguishable row per nomination.

    `nominations` should already be ordered newest-first, so each group's
    first entry is the most recently submitted nomination for that person.

    Returns a list of `{"nominee_name", "nominee_email", "nominations"}`
    dicts, most-supported nominee first.
    """
    groups = {}
    order = []
    for nomination in nominations:
        key = nomination.nominee_email.strip().lower()
        group = groups.get(key)
        if group is None:
            group = {
                "nominee_name": nomination.nominee_name,
                "nominee_email": nomination.nominee_email,
                "nominations": [],
            }
            groups[key] = group
            order.append(key)
        group["nominations"].append(nomination)
    return sorted((groups[key] for key in order), key=lambda group: len(group["nominations"]), reverse=True)


class ServiceAwardRecipient(models.Model):
    """The community member selected to receive the award in a given year.

    One recipient per year, matching the programme's annual $500 award. Set
    by leadership in the admin once a decision is made — this app doesn't
    build the voting itself, only the nomination intake and the record of who
    has already won (so they can be excluded from future cycles).
    """

    recipient_name = models.CharField(max_length=200)
    recipient_email = models.EmailField(blank=True, help_text="Used to exclude them from future nominations.")
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_award_wins",
    )
    nomination = models.ForeignKey(
        ServiceAwardNomination,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="award",
        help_text="The nomination that led to this win, if there was one on file.",
    )
    award_year = models.PositiveIntegerField(unique=True, default=current_award_year)
    notes = models.TextField(blank=True, help_text="Internal notes, e.g. how the payment was made.")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "service award recipient"
        verbose_name_plural = "service award recipients"
        ordering = ["-award_year"]

    def __str__(self):
        return f"{self.recipient_name} ({self.award_year})"
