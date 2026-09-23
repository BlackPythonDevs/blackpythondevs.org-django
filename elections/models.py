"""Council elections: the info page and self-service nomination statements.

This is the mirror image of `nominations` — instead of leadership nominating
someone else for a council seat, a sitting council member (see
`core.models.is_council_member`) writes their own candidacy statement for the
election. Everything else about them (name, photo, affiliations) already
lives on their `core.models.Leader` profile, so `Candidacy` only stores the
statement itself.

Voting isn't built yet — `Election` carries the voting window fields so that
a future `Vote` model can slot in without another migration to this model,
but no ballot logic lives here.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Election(models.Model):
    """One election cycle: a nomination window followed by a voting window."""

    UPCOMING = "upcoming"
    NOMINATING = "nominating"
    BETWEEN = "between"
    VOTING = "voting"
    CLOSED = "closed"

    year = models.PositiveIntegerField(unique=True)
    intro = models.TextField(blank=True, help_text="Optional blurb shown at the top of the election page.")

    nomination_opens_at = models.DateTimeField()
    nomination_closes_at = models.DateTimeField()
    voting_opens_at = models.DateTimeField()
    voting_closes_at = models.DateTimeField()

    class Meta:
        verbose_name = "election"
        verbose_name_plural = "elections"
        ordering = ["-year"]

    def __str__(self):
        return f"{self.year} council election"

    @property
    def phase(self):
        """Where this election is right now, derived from its four dates.

        Kept as a property rather than a stored status so the phase can never
        drift out of sync with the dates that actually define it.
        """
        now = timezone.now()
        if now < self.nomination_opens_at:
            return self.UPCOMING
        if now < self.nomination_closes_at:
            return self.NOMINATING
        if now < self.voting_opens_at:
            return self.BETWEEN
        if now < self.voting_closes_at:
            return self.VOTING
        return self.CLOSED

    @property
    def next_deadline(self):
        """(label, when) for the next boundary this election will cross, or
        `None` once it's closed. Drives the countdown timer on the page."""
        return {
            self.UPCOMING: ("Nominations open", self.nomination_opens_at),
            self.NOMINATING: ("Nominations close", self.nomination_closes_at),
            self.BETWEEN: ("Voting opens", self.voting_opens_at),
            self.VOTING: ("Voting closes", self.voting_closes_at),
        }.get(self.phase)


class Candidacy(models.Model):
    """One council member's statement for one election."""

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="candidacies")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidacies",
    )
    statement = models.TextField(help_text="Why you're running for the council.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "candidacy"
        verbose_name_plural = "candidacies"
        ordering = ["user__display_name"]
        constraints = [
            models.UniqueConstraint(fields=["election", "user"], name="one_candidacy_per_member_per_election")
        ]

    def __str__(self):
        return f"{self.user} ({self.election.year})"

    @property
    def editable(self):
        """Whether the statement can still be changed — only while the
        election this candidacy belongs to is accepting nominations."""
        return self.election.phase == Election.NOMINATING
