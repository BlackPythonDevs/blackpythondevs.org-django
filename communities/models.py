"""Communities: external groups partnered with Black Python Devs.

Each community has one or more community admins — members who can update
their own community's info and message BPD leadership about what's happening
in it. Full CRUD (including deleting a community outright) stays in the
Django admin for staff; the front-end console (see views.py) only ever lets
an admin view/edit their own community and remove themselves from it.

`region` follows `users.regions` (the UN M49 subregion scheme), not
`sponsorships.regions`'s coarser continent scheme — it has to match
`User.region` exactly, since that's what a `CommunityMessage`'s recipients are
filtered on. A community with no fixed location can be marked `is_online`
instead of tied to a country; its messages then reach leadership in every
region rather than being filtered to one.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.utils import timezone
from django_countries.fields import CountryField

from core.models import LEADERSHIP_GROUP_NAME
from users.models import User
from users.regions import region_for_country

# Membership group for the front-end console: like Executor, it carries real
# model permissions (view/change Community — never delete), granted by the
# data migration so admins can use the neapolitan console but never touch the
# Django admin. Synced to CommunityAdmin rows by signals.py.
COMMUNITY_ADMIN_GROUP_NAME = "Community Admins"


def can_manage_community(user):
    """Whether `user` administers at least one community."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=COMMUNITY_ADMIN_GROUP_NAME).exists()


class Community(models.Model):
    """An external community partnered with Black Python Devs."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)

    is_online = models.BooleanField(
        default=False,
        help_text=(
            "Online-only communities aren't tied to one region. Their messages to "
            "leadership reach every region instead of just one."
        ),
    )
    country = CountryField(
        blank=True,
        help_text="Where this community is based. Leave blank for an online-only community.",
    )
    # Derived on save() from country (or forced to "Online"); not edited directly.
    region = models.CharField(max_length=80, blank=True, editable=False)

    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CommunityAdmin",
        related_name="administered_communities",
        blank=True,
    )

    notes = models.TextField(blank=True, help_text="Internal notes. Not shown to community admins.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "community"
        verbose_name_plural = "communities"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_online:
            self.region = "Online"
        elif self.country:
            self.region = region_for_country(self.country.code) or self.region
        super().save(*args, **kwargs)


class CommunityAdmin(models.Model):
    """Grants a user admin rights over one community.

    This row is the only "permission" a community admin needs — see
    signals.py, which keeps the COMMUNITY_ADMIN_GROUP_NAME auth group (and so
    the neapolitan console's model-permission checks) in sync with it.
    """

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="admin_links")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_admin_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["community__name"]
        constraints = [
            models.UniqueConstraint(fields=["community", "user"], name="unique_community_admin"),
        ]

    def __str__(self):
        return f"{self.user} — {self.community}"


class CommunityMessage(models.Model):
    """A message a community admin sends to BPD leadership.

    Sending happens immediately on save, the same as notifications.Notification
    — the site has no task queue and volumes are small enough for a
    synchronous send.
    """

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_community_messages"
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()

    recipient_count = models.PositiveIntegerField(default=0, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject

    def recipients(self):
        """Leadership members in the community's region.

        Always keyed off the *community's* region, never the sending admin's
        own `User.region` — a message is from the community, not from
        whichever admin happens to be logged in. Online communities reach
        leadership in every region instead of being filtered to one.
        """
        qs = User.objects.filter(is_active=True, groups__name=LEADERSHIP_GROUP_NAME).exclude(email="")
        if not self.community.is_online:
            qs = qs.filter(region=self.community.region)
        return qs.distinct()

    def send(self):
        emails = list(self.recipients().values_list("email", flat=True))
        if emails:
            message = EmailMultiAlternatives(
                subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}[{self.community.name}] {self.subject}",
                body=self.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
                bcc=emails,
            )
            message.send()
        self.recipient_count = len(emails)
        self.sent_at = timezone.now()
        self.save(update_fields=["recipient_count", "sent_at"])
        return len(emails)
