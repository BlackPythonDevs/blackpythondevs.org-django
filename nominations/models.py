"""Council nominations: who the current leadership puts forward for a seat on
the Black Python Devs Leadership Council.

Like the sponsorships and ambassadors apps these are plain records, not Wagtail
pages, and they move through a lifecycle — submitted, seconded (which opens a
24-hour objection window), confirmation sent, accepted-pending-onboarding, then
accepted (or declined/withdrawn at various points). A nominator can withdraw
their own nomination while it is still open.

Nominating and seconding are restricted to the people already in leadership:
members of the "Leadership Council" group (see `core.models`). That's a
membership group that deliberately carries no permissions, so the views gate
on group membership rather than on Django model permissions. Raising an
objection during the window is open to a wider tier — Council *and* Executor
(`core.models.is_leadership_or_above`) — since objecting is a lighter-weight
check than nominating or seconding.

The nominee is stored as a name and email rather than a `User` FK, because
plenty of the people worth nominating have no account here yet. `nominee_user`
links the record to an account when there is one, so a nominee who is already a
member can be recognised. Once the nomination is confirmed, `invite_link`
carries the actual account-creation/group-assignment link (see
`users.models.InviteLink`) — that's how "click a link, get an account and the
council group" is implemented, without duplicating InviteLink's logic here.
"""

import datetime as dt

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import COUNCIL_GROUP_NAME, ONBOARDING_GROUP_NAME, is_leadership_or_above

# How long the objection window stays open after a nomination is seconded.
OBJECTION_WINDOW = dt.timedelta(hours=24)


def can_nominate(user):
    """Whether `user` may nominate someone for the council.

    Superusers pass so a site admin is never locked out of their own console.
    Seconding uses this same check — a second is just another Council-tier
    leader, not a wider tier.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=COUNCIL_GROUP_NAME).exists()


def current_term_year():
    """Default nomination cycle: the current calendar year."""
    return timezone.now().year


def notify_onboarding_team(nomination, request):
    """Email everyone on the Onboarding Team that `nomination`'s announcement
    draft and profile photo are ready, so they can build the matching social
    post from the same content. Synchronous, same idiom as
    `notifications.Notification.send()` — this site has no task queue.
    """
    from django.contrib.auth import get_user_model
    from django.core.mail import EmailMultiAlternatives

    emails = list(
        get_user_model()
        .objects.filter(groups__name=ONBOARDING_GROUP_NAME, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    if not emails:
        return

    page_url = request.build_absolute_uri(reverse("wagtailadmin_pages:edit", args=[nomination.announcement_page_id]))
    message = EmailMultiAlternatives(
        subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}Ready to announce: {nomination.nominee_name}",
        body=(
            f"{nomination.nominee_name}'s profile photo is in and their announcement draft is ready.\n\n"
            f"Edit the draft: {page_url}\n\n"
            "Feel free to use the same content for the social media post."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=emails,
    )
    message.send()


class CouncilNomination(models.Model):
    """One leader's nomination of one person for the Leadership Council."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "review"
    SECONDED = "seconded"
    CONFIRMATION_SENT = "confirmation_sent"
    ACCEPTED_PENDING_ONBOARDING = "accepted_pending_onboarding"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    STATUS_CHOICES = [
        (SUBMITTED, "Submitted"),
        (UNDER_REVIEW, "Under review"),
        (SECONDED, "Seconded — objection window open"),
        (CONFIRMATION_SENT, "Confirmation sent to nominee"),
        (ACCEPTED_PENDING_ONBOARDING, "Accepted — completing onboarding"),
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
        max_length=30,
        choices=STATUS_CHOICES,
        default=SUBMITTED,
        db_index=True,
    )
    notes = models.TextField(blank=True, help_text="Internal notes. Not shown to the nominee.")

    seconded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="council_nominations_seconded",
        help_text="The other Council-tier leader who seconded this nomination.",
    )
    seconded_at = models.DateTimeField(null=True, blank=True)
    objection_window_closes_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set to 24 hours after seconding. Objections can be raised until this passes.",
    )
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    invite_link = models.ForeignKey(
        "users.InviteLink",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="council_nomination",
        help_text="The invite emailed to the nominee to accept their council seat.",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    announcement_page = models.ForeignKey(
        "blog.BlogPage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Draft announcement created once onboarding (profile + photo) is complete.",
    )
    onboarding_notified_at = models.DateTimeField(null=True, blank=True)

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

    def can_second(self, user):
        """Whether `user` may second this nomination: another Council-tier
        leader, not the original nominator, while it's still awaiting a second.
        """
        if self.status != self.SUBMITTED:
            return False
        if user.is_authenticated and user.pk == self.nominator_id:
            return False
        return can_nominate(user)

    def second(self, user):
        """Record `user` as the seconder and open the 24-hour objection window."""
        self.seconded_by = user
        self.seconded_at = timezone.now()
        self.objection_window_closes_at = self.seconded_at + OBJECTION_WINDOW
        self.status = self.SECONDED
        self.save(update_fields=["seconded_by", "seconded_at", "objection_window_closes_at", "status", "updated_at"])

    @property
    def objection_window_open(self):
        """Whether an objection can still be raised right now."""
        return (
            self.status == self.SECONDED
            and self.objection_window_closes_at is not None
            and timezone.now() < self.objection_window_closes_at
        )

    @property
    def ready_to_confirm(self):
        """Whether the objection window has closed and confirmation can be sent.

        A property rather than a stored flag, same reasoning as
        `elections.Election.phase` — it can never drift out of sync with the
        timestamp that actually defines it.
        """
        return (
            self.status == self.SECONDED
            and self.objection_window_closes_at is not None
            and timezone.now() >= self.objection_window_closes_at
        )

    def can_object(self, user):
        """Whether `user` may raise an objection right now: Council or
        Executor (a wider tier than nominating/seconding), only while the
        window is open.
        """
        return self.objection_window_open and is_leadership_or_above(user)

    def create_confirmation_invite(self, sent_by):
        """Create the email-locked, single-use invite that lets the nominee
        accept their council seat. Doesn't send anything or change this
        nomination's own state — the caller (a view, which has the request)
        builds the absolute URL, emails it, and calls `mark_confirmation_sent`.
        """
        from django.contrib.auth.models import Group

        from users.models import InviteLink

        invite = InviteLink.objects.create(email=self.nominee_email, created_by=sent_by, max_uses=1)
        invite.groups.add(Group.objects.get(name=COUNCIL_GROUP_NAME))
        return invite

    def mark_confirmation_sent(self, invite):
        self.invite_link = invite
        self.confirmation_sent_at = timezone.now()
        self.status = self.CONFIRMATION_SENT
        self.save(update_fields=["invite_link", "confirmation_sent_at", "status", "updated_at"])

    def mark_accepted_pending_onboarding(self):
        """The nominee clicked the link and their account exists/is linked.
        They still need to fill in their profile + headshot before this
        counts as fully accepted (see `complete_onboarding`)."""
        self.status = self.ACCEPTED_PENDING_ONBOARDING
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at", "updated_at"])

    def complete_onboarding(self, leader, request):
        """The nominee has filled in their profile and uploaded a headshot
        (`leader` is their `core.models.Leader` roster entry). Draft the
        announcement post and let the onboarding team know it's ready.

        No-ops without a photo, or if this has already run — `leader` gets
        saved again on later profile edits, and this should only fire once.
        """
        if self.onboarding_notified_at is not None:
            return
        if not leader.photo:
            return

        from blog.models import BlogIndexPage, BlogPage

        index_page = BlogIndexPage.objects.first()
        if index_page is None:
            return

        page = BlogPage(
            title=f"Welcome {self.nominee_name} to the Leadership Council",
            date=timezone.now().date(),
            description=self.statement,
            featured_image=leader.photo,
            live=False,
        )
        index_page.add_child(instance=page)
        page.save_revision()

        self.announcement_page = page
        self.status = self.ACCEPTED
        self.onboarding_notified_at = timezone.now()
        self.save(update_fields=["announcement_page", "status", "onboarding_notified_at", "updated_at"])

        notify_onboarding_team(self, request)


class NominationObjection(models.Model):
    """An objection raised during a nomination's 24-hour window.

    Shown only to the Leadership Council/Executor members reviewing the
    nomination — never to the nominee or the public. `submitted_by` keeps
    the submitter accountable in the database even though the review UI
    doesn't surface their name to whoever's deciding whether to still send
    the confirmation: "anonymous" here means anonymous to the nominee, not
    to the system.
    """

    nomination = models.ForeignKey(CouncilNomination, on_delete=models.CASCADE, related_name="objections")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="council_nomination_objections",
    )
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Objection to {self.nomination.nominee_name}"
