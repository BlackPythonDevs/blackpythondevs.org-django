"""The Executorship Election: the info page and self-service nomination
statements for whoever the council will choose as the next Executor.

This is the mirror image of `nominations` — instead of leadership nominating
someone else for a council seat, a sitting council member (see
`core.models.is_council_member`) writes their own candidacy statement to
become Executor. Everything else about them (name, photo, affiliations)
already lives on their `core.models.Leader` profile, so `Candidacy` only
stores the statement itself.

Voting isn't built yet — `Election` carries the voting window fields so that
a future `Vote` model can slot in without another migration to this model,
but no ballot logic lives here.
"""

import datetime as dt
import secrets

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

# Being fair to every timezone means each boundary has to look at whichever
# zone is most generous in *that* direction — and the two directions are not
# the same zone:
#
# - Opening: the window should open as soon as its date has begun ANYWHERE —
#   the *first* zone to reach it, UTC+14 (Kiritimati / Line Islands) — so
#   nobody's local "it's not that date yet" makes them miss an early start.
# - Closing: the window should stay open as long as its date is still going
#   ANYWHERE — the *last* zone to leave it, UTC-12 (Baker/Howland Islands).
#   This is "AOE" ("Anywhere on Earth"), the standard deadline convention —
#   so nobody's local "it's already the next date" cuts them off early.
#
# Anchoring both to the same zone would make one of the two directions mean
# "everywhere" instead of "anywhere" — e.g. opening on AOE (UTC-12) would
# open only once the date has begun *everywhere*, the opposite of generous.
EARLIEST_TZ = dt.timezone(dt.timedelta(hours=14))
AOE = dt.timezone(dt.timedelta(hours=-12))


def default_election_year():
    """Elections are set up ahead of time — next year, not this one."""
    return timezone.now().year + 1


def _local_midnight(date, tz):
    return dt.datetime.combine(date, dt.time.min, tzinfo=tz).astimezone(dt.UTC)


def opens_instant(date):
    """The UTC instant `date` begins ANYWHERE on Earth. A window that opens
    on `date` opens at this instant."""
    return _local_midnight(date, EARLIEST_TZ)


def closes_instant(date):
    """The UTC instant `date` has ended ANYWHERE on Earth (AOE). A window
    that closes on `date` closes at this instant — the moment AOE reaches
    the day after `date`."""
    return _local_midnight(date + dt.timedelta(days=1), AOE)


def election_window_instants(nomination_opens, nomination_closes, voting_opens, voting_closes):
    """Turn the four dates a person actually enters (in the admin, or via
    `create_election`) into the four UTC instants `Election` stores,
    validating their order along the way.

    Shared by `elections.forms.ElectionAdminForm` and `create_election` so
    the two can't drift into checking different things. Returns
    `(instants, errors)` — `errors` maps a date's name to what's wrong with
    it; `instants` is only complete/correct once `errors` is empty.

    Note: because opens and closes use different zones, a voting window
    that opens on the date right after (or the same date as) nominations
    close will overlap with it by up to a bit over a day — that's the
    unavoidable price of being maximally generous in both directions at
    once, not a mistake, so it's left to the caller to warn about rather
    than treated as an error here.
    """
    instants = {
        "nomination_opens": opens_instant(nomination_opens),
        "nomination_closes": closes_instant(nomination_closes),
        "voting_opens": opens_instant(voting_opens),
        "voting_closes": closes_instant(voting_closes),
    }
    errors = {}
    if instants["nomination_opens"] >= instants["nomination_closes"]:
        errors["nomination_closes"] = "Must be after the date nominations open."
    if instants["voting_opens"] >= instants["voting_closes"]:
        errors["voting_closes"] = "Must be after the date voting opens."
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
        return f"{self.year} Executorship Election"

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

    def has_voted(self, user):
        """Whether `user` has already cast a ballot in this election.

        Checked against `VoteRecord`, never against `Ballot` — that's the
        whole point of keeping the two apart. See `VoteRecord`.
        """
        return self.vote_records.filter(user=user).exists()


class Candidacy(models.Model):
    """One council member's candidacy statement for the Executorship Election."""

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="candidacies")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidacies",
    )
    statement = models.TextField(help_text="Why you're running to be Executor.")

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


def _ballot_token():
    return secrets.token_urlsafe(32)


class Ballot(models.Model):
    """One anonymous ranked-choice ballot cast in an Executorship Election's
    voting window.

    Deliberately carries no field pointing back to the voter. `VoteRecord`
    is the only thing that enforces one ballot per council member, and it
    lives in a separate table so there's no join — accidental or
    deliberate — from "who voted" to "how they ranked candidates".
    `elections.views.BallotCastView` creates both rows in the same request,
    but nothing in the schema itself connects them afterward.
    """

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="ballots")
    token = models.CharField(max_length=64, unique=True, default=_ballot_token, editable=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ballot"
        verbose_name_plural = "ballots"

    def __str__(self):
        return f"Ballot {self.token[:8]}… ({self.election.year})"


class BallotRanking(models.Model):
    """One candidate's place (1 = first choice) on one anonymous `Ballot`,
    *within their own region's race*.

    Each region elects its own representative — one ballot carries a
    separate ranking per region, not one combined list for a single seat.
    `rank` is therefore only required to be unique among a ballot's
    candidates who share a region (enforced in `elections.forms.BallotForm`,
    not at the database level, since region lives on `candidacy.user`
    rather than on this row); the same number can and does recur across
    different regions on the same ballot.
    """

    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name="rankings")
    candidacy = models.ForeignKey(Candidacy, on_delete=models.CASCADE, related_name="rankings")
    rank = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "ballot ranking"
        verbose_name_plural = "ballot rankings"
        ordering = ["ballot_id", "rank"]
        constraints = [
            models.UniqueConstraint(fields=["ballot", "candidacy"], name="one_ranking_per_candidate_per_ballot"),
        ]

    def __str__(self):
        return f"#{self.rank}: {self.candidacy}"


class VoteRecord(models.Model):
    """That `user` cast a ballot in `election` — nothing more.

    This is what `Election.has_voted` and `elections.views.VotingWindowRequiredMixin`
    check to stop a council member voting twice. It's kept apart from
    `Ballot`/`BallotRanking` on purpose — see `Ballot`'s docstring.
    """

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="vote_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="election_votes")
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vote record"
        verbose_name_plural = "vote records"
        constraints = [models.UniqueConstraint(fields=["election", "user"], name="one_vote_per_member_per_election")]

    def __str__(self):
        return f"{self.user} voted ({self.election.year})"


def _region_of(candidacy):
    return candidacy.user.region or "Unspecified region"


def tally_irv(election, candidacies=None):
    """Run instant-runoff tabulation over every ballot cast in `election`,
    restricted to `candidacies` (every candidate in the election if not
    given). Pass one region's candidacies to tally just that region's
    race — see `regional_results`, which is what actually does that; this
    function doesn't care whether `candidacies` spans one region or all of
    them, it just counts whichever candidates it's handed.

    Each round tallies every remaining candidate's current first choice
    among ballots that still have one (a ballot that ranked none of the
    candidates still standing is "exhausted" and simply stops counting,
    same as any IRV tally). A candidate with a strict majority of the
    non-exhausted ballots wins; otherwise the round's last-place candidate
    is eliminated and the next round runs on whoever's left.

    Returns a list of rounds, each `{"counts": {candidacy: n, ...},
    "eliminated": candidacy_or_None, "winner": candidacy_or_None}`, keyed by
    `Candidacy` instances rather than ids so callers don't have to re-fetch
    them. The last round either has a `winner` or, if candidates keep
    tying for last with no ballots left to separate them, ends with
    `remaining` down to whoever's left standing.
    """
    if candidacies is None:
        candidacies = election.candidacies.all()
    candidacies = {c.pk: c for c in candidacies}

    ballots = []
    for ballot in election.ballots.prefetch_related("rankings"):
        ordered = [
            r.candidacy_id for r in sorted(ballot.rankings.all(), key=lambda r: r.rank) if r.candidacy_id in candidacies
        ]
        ballots.append(ordered)

    remaining = set(candidacies)
    rounds = []
    while remaining:
        counts = dict.fromkeys(remaining, 0)
        for ordered in ballots:
            choice = next((c for c in ordered if c in remaining), None)
            if choice is not None:
                counts[choice] += 1

        total = sum(counts.values())
        winner = None
        if total and max(counts.values()) * 2 > total:
            winner = max(counts, key=counts.get)

        eliminated = None
        if winner is None and len(remaining) > 1:
            eliminated = min(counts, key=counts.get)

        rounds.append(
            {
                "counts": {candidacies[cid]: n for cid, n in counts.items()},
                "eliminated": candidacies[eliminated] if eliminated is not None else None,
                "winner": candidacies[winner] if winner is not None else None,
            }
        )

        if winner is not None or eliminated is None:
            break
        remaining.remove(eliminated)

    return rounds


def regional_results(election):
    """`{region: rounds}` for every region with candidates in `election` —
    one independent instant-runoff race per region, tallied from the same
    ballots (see `BallotRanking`), sorted by region name for a stable
    display order."""
    by_region = {}
    for candidacy in election.candidacies.select_related("user"):
        by_region.setdefault(_region_of(candidacy), []).append(candidacy)
    return {region: tally_irv(election, candidacies) for region, candidacies in sorted(by_region.items())}
