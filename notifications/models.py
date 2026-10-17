"""Broadcast messages to a filtered slice of the membership, and each
member's own in-app notification feed.

`Notification` (below): staff, Executors, Sponsors, and Community Partners
can each send an announcement to members matching a set of filters — region,
group membership ("roles"), and subcommunity ("affinities"). Sponsors and
Community Partners are membership groups like Ambassadors or the Leadership
Council: they carry no permissions of their own, are provisioned by a data
migration, and views gate on membership rather than on model permissions.

Sending happens immediately on save: the model resolves the matching `User`
queryset and emails them right away rather than queuing anything, since the
site has no task queue and the membership is small enough that a synchronous
send is fine.

`body` is stored as Markdown rather than edited through Wagtail's Draftail
widget: Sponsors and Community Partners send from here too, and they don't
have Wagtail admin access, which Draftail's own image chooser requires. A
plain textarea plus a client-side preview works the same for every sender.

`UserNotification` (see issue #98) is one item in a single member's own
in-app feed — "so-and-so mentioned you", or (since #133) an announcement
broadcast they were a recipient of. Deliberately generic (a plain message +
optional link + optional actor, no typed "kind" field) so a new feature
anywhere in the project can create one with `notify(...)` without this app
needing to know what it's about — the same reasoning as
checklists.models.Note's generic relation.
"""

import bleach
import markdown
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.postgres.fields import ArrayField
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from core.mail import UNMANAGED_MAILBOX_FOOTER, absolute_url
from users.models import User

# Same extension set as the static-site markdown import (see
# core.management.commands.import_content) so authoring conventions match.
MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "attr_list"]

# Tags/attributes the composer's Markdown pipeline (MARKDOWN_EXTENSIONS) can
# actually produce: paragraphs, inline formatting, links, fenced code, lists,
# tables, and the composer's own inserted images. Anything else — in
# particular raw HTML a sender typed, or attributes slipped in via the
# `attr_list` extension (e.g. `onerror=`) — is stripped by `body_html_safe`
# before ever reaching a viewer's browser. Shared with
# community_messages, whose composer is the same markdown-with-preview form.
ALLOWED_MESSAGE_HTML_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "a",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "img",
]
ALLOWED_MESSAGE_HTML_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
}

# Membership groups, like COUNCIL_GROUP_NAME in core.models: no permissions of
# their own, provisioned by a data migration, granted by hand in the admin.
SPONSOR_GROUP_NAME = "Sponsors"
COMMUNITY_PARTNER_GROUP_NAME = "Community Partners"

# Groups (beyond staff/superuser) allowed onto the send-message page at all.
# "Executor" is provisioned by sponsorships' own migration.
SENDER_GROUP_NAMES = ("Executor", SPONSOR_GROUP_NAME, COMMUNITY_PARTNER_GROUP_NAME)


def can_send_notifications(user):
    """Whether `user` may open the notifications tool at all."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=SENDER_GROUP_NAMES).exists()


def has_full_access(user):
    """Staff, superusers, and Executors can filter freely on every axis."""
    return user.is_superuser or user.is_staff or user.groups.filter(name="Executor").exists()


def is_sponsor(user):
    return user.groups.filter(name=SPONSOR_GROUP_NAME).exists()


def is_community_partner(user):
    return user.groups.filter(name=COMMUNITY_PARTNER_GROUP_NAME).exists()


class Notification(models.Model):
    """One broadcast message and the filters used to pick its recipients."""

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_notifications",
    )
    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Markdown. Images become ![](url) — attach one below and it's added for you.")

    # Recipient filters. Empty means "don't filter on this axis" for all
    # three — a notification with nothing set reaches every active member.
    regions = ArrayField(
        models.CharField(max_length=40),
        blank=True,
        default=list,
        help_text="Limit to members in these regions. Leave empty for every region.",
    )
    roles = models.ManyToManyField(
        Group,
        blank=True,
        related_name="+",
        help_text="Limit to members of these groups. Leave empty to skip this filter.",
    )
    affinities = ArrayField(
        models.CharField(max_length=40, choices=User.SUBCOMMUNITY_CHOICES),
        blank=True,
        default=list,
        help_text="Limit to members who identify with these subcommunities.",
    )

    recipient_count = models.PositiveIntegerField(default=0, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject

    @property
    def body_html(self):
        """`body` rendered from Markdown, for the HTML half of the email."""
        return markdown.markdown(self.body, extensions=MARKDOWN_EXTENSIONS)

    @property
    def body_html_safe(self):
        """`body_html`, sanitized for rendering on a page.

        The outgoing email can use `body_html` as-is (a mail client is the
        only reader), but this detail page — the one the email links back to
        — renders in a browser, so raw HTML the sender typed must be stripped
        first. Same pipeline as community_messages.CommunityMessage.
        """
        return bleach.clean(
            self.body_html,
            tags=ALLOWED_MESSAGE_HTML_TAGS,
            attributes=ALLOWED_MESSAGE_HTML_ATTRIBUTES,
            strip=True,
        )

    @property
    def view_url(self):
        """Absolute URL of the on-site page for this notification (issue #132)."""
        return absolute_url(reverse("notifications:detail", args=[self.pk]))

    def email_parts(self):
        """The email's plain-text and HTML bodies, preamble and footer wrapped
        around the message itself (issue #132): these emails come from one
        unmanaged mailbox, so every one says what it is, who sent it, where to
        read it on the site, and that replies are discarded."""
        plain = (
            f"This is a Notification sent by {self.sender} via BlackPythonDevs.org\n"
            f"You can view the notification at: {self.view_url}\n"
            f"\n"
            f"{self.body}\n"
            f"\n"
            f"--\n"
            f"{UNMANAGED_MAILBOX_FOOTER}"
        )
        html = (
            f"<p>This is a Notification sent by {escape(str(self.sender))} via BlackPythonDevs.org<br>"
            f'You can view the notification at: <a href="{self.view_url}">{self.view_url}</a></p>'
            f"{self.body_html}"
            f"<p>{escape(UNMANAGED_MAILBOX_FOOTER)}</p>"
        )
        return plain, html

    def recipients(self):
        """The `User` queryset matching this notification's filters."""
        qs = User.objects.filter(is_active=True).exclude(email="")
        if self.regions:
            qs = qs.filter(region__in=self.regions)
        if self.affinities:
            qs = qs.filter(subcommunities__overlap=self.affinities)
        if self.pk and self.roles.exists():
            qs = qs.filter(groups__in=self.roles.all())
        return qs.distinct()

    def send(self):
        """Email every matching member right away and record the outcome.

        Recipients go in `bcc` (with the message addressed to the sending
        address itself) so members targeted by the same announcement don't
        see each other's addresses.

        Each recipient also gets an entry in their in-app inbox (issue #133):
        before, broadcasts existed only as email and on the sender-facing
        archive, so /notifications/ showed an announcement the recipient's
        own inbox had no trace of.
        """
        recipients = list(self.recipients())
        emails = [user.email for user in recipients]
        if emails:
            plain, html = self.email_parts()
            message = EmailMultiAlternatives(
                subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}{self.subject}",
                body=plain,  # plain text: preamble, raw-Markdown body, footer
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
                bcc=emails,
            )
            message.attach_alternative(html, "text/html")
            message.send()
        self.recipient_count = len(emails)
        self.sent_at = timezone.now()
        self.save(update_fields=["recipient_count", "sent_at"])

        # bulk_create rather than per-recipient notify() calls — one query
        # instead of N for what can be the whole membership. Like the email
        # half, this ignores app_communication_preferences: there's no switch
        # for it yet (see issue #98's "out of scope" note).
        if recipients:
            detail_url = reverse("notifications:detail", args=[self.pk])
            UserNotification.objects.bulk_create(
                UserNotification(recipient=user, message=self.subject, url=detail_url) for user in recipients
            )
        return len(emails)


class UserNotification(models.Model):
    """One item in one member's own in-app notification feed."""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="app_notifications")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self):
        return self.message

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])


def notify(recipient, message, *, actor=None, url=""):
    """Create one in-app notification for `recipient`.

    The one entry point other apps should use rather than creating
    `UserNotification` rows directly — see checklists.mentions for the first
    caller. Never raises on a recipient with notifications disabled at the
    Django level; there's no such switch yet (see issue #98's "out of scope"
    note about `app_communication_preferences`), so this always creates the
    row for now.
    """
    return UserNotification.objects.create(recipient=recipient, actor=actor, message=message, url=url)
