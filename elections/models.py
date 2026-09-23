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

import datetime as dt

import bleach
import markdown
from django.conf import settings
from django.db import models
from django.utils import timezone

from notifications.models import MARKDOWN_EXTENSIONS

# Tags/attributes the Markdown pipeline (MARKDOWN_EXTENSIONS) can actually
# produce for a short blurb: paragraphs, inline formatting, links, and lists.
# Anything else — raw HTML an admin pasted in, or attributes slipped in via
# the `attr_list` extension — is stripped by `intro_html` before this ever
# reaches a visitor's browser, same reasoning as
# `community_messages.CommunityMessage.body_html_safe`.
ALLOWED_INTRO_HTML_TAGS = ["p", "br", "strong", "em", "a", "code", "ul", "ol", "li", "blockquote"]
ALLOWED_INTRO_HTML_ATTRIBUTES = {"a": ["href", "title"]}

# "Anywhere on Earth" (AOE, UTC-12): the standard convention for a deadline
# that isn't over until it's over for literally everyone, since UTC-12 is the
# last timezone still on any given date. `create_election` anchors *every*
# window boundary — both opens and closes — to AOE, so a window never opens
# before its date has begun everywhere, and never closes before its date has
# ended everywhere.
AOE = dt.timezone(dt.timedelta(hours=-12))


def default_election_year():
    """Elections are set up ahead of time — next year, not this one."""
    return timezone.now().year + 1


def aoe_instant(date):
    """The UTC instant local midnight (00:00) arrives on `date`, AOE.

    A window that *opens* on `date` opens at `aoe_instant(date)`. A window
    that *closes* on `date` closes at `aoe_instant(date + one day)` — the
    start of the next date, AOE, i.e. the moment `date` has fully ended.
    """
    local_midnight = dt.datetime.combine(date, dt.time.min, tzinfo=AOE)
    return local_midnight.astimezone(dt.UTC)


def election_window_instants(nomination_opens, nomination_closes, voting_opens, voting_closes):
    """Turn the four AOE dates a person actually enters (in the admin, or via
    `create_election`) into the four UTC instants `Election` stores,
    validating their order along the way.

    Shared by `elections.forms.ElectionAdminForm` and `create_election` so
    the two can't drift into checking different things. Returns
    `(instants, errors)` — `errors` maps a date's name to what's wrong with
    it; `instants` is only complete/correct once `errors` is empty.
    """
    instants = {
        "nomination_opens": aoe_instant(nomination_opens),
        "nomination_closes": aoe_instant(nomination_closes + dt.timedelta(days=1)),
        "voting_opens": aoe_instant(voting_opens),
        "voting_closes": aoe_instant(voting_closes + dt.timedelta(days=1)),
    }
    errors = {}
    if instants["nomination_opens"] >= instants["nomination_closes"]:
        errors["nomination_closes"] = "Must be after the date nominations open."
    if instants["voting_opens"] >= instants["voting_closes"]:
        errors["voting_closes"] = "Must be after the date voting opens."
    if instants["voting_opens"] < instants["nomination_closes"]:
        errors["voting_opens"] = "Must be on or after the date nominations close."
    return instants, errors


class Election(models.Model):
    """One election cycle: a nomination window followed by a voting window."""

    UPCOMING = "upcoming"
    NOMINATING = "nominating"
    BETWEEN = "between"
    VOTING = "voting"
    CLOSED = "closed"

    year = models.PositiveIntegerField(unique=True, default=default_election_year)
    intro = models.TextField(blank=True, help_text="Optional blurb shown at the top of the election page. Markdown.")

    nomination_opens_at = models.DateTimeField()
    nomination_closes_at = models.DateTimeField()
    voting_opens_at = models.DateTimeField()
    voting_closes_at = models.DateTimeField()

    class Meta:
        db_table = "executor_elections"
        verbose_name = "election"
        verbose_name_plural = "elections"
        ordering = ["-year"]

    def __str__(self):
        return f"{self.year} council election"

    @property
    def intro_html(self):
        """`intro` rendered from Markdown and sanitized for display on the
        public election page — authored in the Django admin, but by whoever
        currently has staff access, not necessarily by someone who should be
        able to inject arbitrary HTML into a page every visitor loads."""
        if not self.intro:
            return ""
        html = markdown.markdown(self.intro, extensions=MARKDOWN_EXTENSIONS)
        return bleach.clean(html, tags=ALLOWED_INTRO_HTML_TAGS, attributes=ALLOWED_INTRO_HTML_ATTRIBUTES, strip=True)

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
