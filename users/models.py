import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django_countries.fields import CountryField

from .regions import region_for_country

# How long a generated invite link stays valid if it isn't used.
INVITE_LINK_EXPIRY_DAYS = 7

# Session key users.forms.SignupForm checks to apply a pending signup link's
# groups once an account is found or created. Set by the redirect in
# users.views.invite_accept for a link that isn't locked to one email.
INVITE_SESSION_KEY = "pending_invite_token"


def _invite_token():
    return secrets.token_urlsafe(32)


def _invite_expiry():
    return timezone.now() + timedelta(days=INVITE_LINK_EXPIRY_DAYS)


def _all_communication_preferences():
    """Default for `app_communication_preferences`: app notifications start on
    for every topic, unlike email which starts opted-out (see User.communication_preferences).
    """
    return [key for key, _ in User.COMMUNICATION_PREFERENCE_CHOICES]


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
        help_text="What you'd like emailed to you.",
    )
    # Same topics as communication_preferences, but for in-app notifications
    # rather than email. Starts with everything on (opt-out), while email
    # starts opted-out, since app notifications are lower-friction.
    app_communication_preferences = ArrayField(
        models.CharField(max_length=40, choices=COMMUNICATION_PREFERENCE_CHOICES),
        blank=True,
        default=_all_communication_preferences,
        help_text="What you'd like as app notifications.",
    )
    onboarding_completed_at = models.DateTimeField(null=True, blank=True, editable=False)

    # Editable from the member profile page, but only for Leadership and
    # above — see core.models.is_leadership_or_above.
    twitter = models.URLField("Twitter/X", blank=True)
    mastodon = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)

    def __str__(self):
        return self.display_name or self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if self.country:
            self.region = region_for_country(self.country.code) or self.region
        super().save(*args, **kwargs)

    @property
    def needs_onboarding(self):
        return self.onboarding_completed_at is None


class InviteLink(models.Model):
    """A link a staff member sends to bring people in with groups pre-applied.

    Only staff/superusers can create these (see users.admin.InviteLinkAdmin), and a
    non-superuser can only bake in groups they themselves belong to, so no one can use
    an invite to hand out access they don't already have.

    Set `email` to lock the link to one person: visiting it directly creates or logs
    into that account. Leave `email` blank to make a general-purpose signup link that
    anyone can use — visiting it hands off to the normal signup form, and this
    invite's groups are applied to whichever account comes out of that (new or
    already existing; see users.forms.SignupForm and `consume_pending`).

    Every link must have a `max_uses`, an `expires_at`, or both — one of the two has
    to bound it, so a forgotten or leaked link doesn't stay a standing risk forever.
    """

    email = models.EmailField(
        blank=True,
        help_text="Leave blank for a general-purpose signup link anyone can use. "
        "Set an address to invite one specific person — the link will only work for that email.",
    )
    groups = models.ManyToManyField(
        Group, blank=True, help_text="Groups applied to the account automatically when the invite is accepted."
    )
    token = models.CharField(max_length=64, unique=True, editable=False, default=_invite_token)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invites")
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=1,
        help_text="How many times this link can be used. Leave blank for unlimited uses "
        "(the expiration date is then the only limit).",
    )
    use_count = models.PositiveIntegerField(default=0, editable=False)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_invite",
        editable=False,
        help_text="Most recent account this link was used for.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        default=_invite_expiry,
        help_text="When this link stops working. Leave blank for no date limit "
        "(the uses limit is then the only limit).",
    )
    used_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite for {self.email}" if self.email else f"Signup link ({self.use_count} uses)"

    def get_absolute_url(self):
        return reverse("invite-accept", args=[self.token])

    def clean(self):
        super().clean()
        if self.max_uses is None and self.expires_at is None:
            raise ValidationError("Set a uses limit, an expiration date, or both.")

    @property
    def is_expired(self):
        return self.expires_at is not None and timezone.now() >= self.expires_at

    @property
    def is_exhausted(self):
        return self.max_uses is not None and self.use_count >= self.max_uses

    @property
    def is_valid(self):
        return not self.is_exhausted and not self.is_expired

    def apply_to(self, user):
        """Apply this invite's groups to `user` and record one use. Caller is
        responsible for checking `is_valid` first — this doesn't re-check.
        """
        user.groups.add(*self.groups.all())
        self.use_count += 1
        self.used_at = timezone.now()
        self.accepted_by = user
        self.save(update_fields=["use_count", "used_at", "accepted_by"])

    def accept(self, request):
        """Find-or-create the account for this invite's (fixed) email, apply its
        groups, and record the use. Returns the User. Only for an email-locked
        invite — a general signup link goes through `consume_pending` instead.
        """
        from allauth.account.adapter import get_adapter
        from allauth.account.utils import filter_users_by_email

        existing = filter_users_by_email(self.email, prefer_verified=True)
        if existing:
            user = existing[0]
        else:
            adapter = get_adapter(request)
            user = User(email=self.email)
            adapter.populate_username(request, user)
            user.set_unusable_password()
            user.save()

        self.apply_to(user)
        return user

    @classmethod
    def consume_pending(cls, request, user):
        """Apply the signup link stashed in the session (by the redirect in
        users.views.invite_accept) to `user`, whether they just signed up or already
        had an account. No-op if nothing is pending or it's no longer valid.
        """
        token = request.session.pop(INVITE_SESSION_KEY, None)
        if not token:
            return
        invite = cls.objects.filter(token=token).first()
        if invite is not None and invite.is_valid:
            invite.apply_to(user)
