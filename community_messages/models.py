"""Messages a community admin sends to BPD leadership.

Deliberately a separate app from `communities`: that app owns the community
roster (who a community is, who admins it); this one owns a single
send-and-record flow layered on top, the same relationship `notifications` has
to `users`/`auth` (it doesn't own a roster either — it just sends to a
filtered slice of it).

This is also *not* the same direction as `notifications.Notification`: that
app broadcasts announcements down to the membership (staff/Executor/Sponsor/
Community Partner -> members). A `CommunityMessage` goes the other way,
up to leadership from one specific community's admin — different enough
(fixed single recipient axis, tied to one `Community` instance) that reusing
`Notification` directly would mean bolting community-specific fields onto an
app whose job is generic broadcast, rather than keeping the two concerns apart.
"""

import bleach
import markdown
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models import Q
from django.utils import timezone

from communities.models import Community
from core.models import LEADERSHIP_GROUP_NAME
from notifications.models import MARKDOWN_EXTENSIONS
from users.models import User

# Tags/attributes the composer's Markdown pipeline (MARKDOWN_EXTENSIONS) can
# actually produce: paragraphs, inline formatting, links, fenced code, lists,
# tables, and the composer's own inserted images. Anything else — in
# particular raw HTML a sender typed, or attributes slipped in via the
# `attr_list` extension (e.g. `onerror=`) — is stripped by body_html_safe
# before ever reaching another viewer's browser.
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


def is_leadership(user):
    """Whether `user` is a plain (non-staff) recipient of these messages."""
    return user.is_authenticated and user.groups.filter(name=LEADERSHIP_GROUP_NAME).exists()


def messages_for_leader(user):
    """Sent messages `user` is a recipient of, as a member of Leadership.

    Mirrors `CommunityMessage.recipients()`'s own logic (region match, or any
    community marked online) but the other way round — from "which messages
    reach this leader" instead of "which leaders does this message reach" —
    since this drives a queryset rather than a single instance's audience.
    """
    if not (user.is_superuser or is_leadership(user)):
        return CommunityMessage.objects.none()
    return CommunityMessage.objects.filter(sent_at__isnull=False).filter(
        Q(community__is_online=True) | Q(community__region=user.region)
    )


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

    @property
    def body_html(self):
        """`body` rendered from Markdown, for the HTML half of the email —
        same pipeline as `notifications.Notification.body_html`, since the
        compose form is the same markdown-editor-with-preview composer."""
        return markdown.markdown(self.body, extensions=MARKDOWN_EXTENSIONS)

    @property
    def body_html_safe(self):
        """`body_html`, sanitized for rendering on a page.

        Unlike the outgoing email — where `body_html` is only ever read by a
        mail client, never executed as page script — a viewer here might be a
        *different* admin of the same community, or a Leadership member. Raw
        HTML the sender typed must never reach their browser unsanitized.
        """
        return bleach.clean(
            self.body_html,
            tags=ALLOWED_MESSAGE_HTML_TAGS,
            attributes=ALLOWED_MESSAGE_HTML_ATTRIBUTES,
            strip=True,
        )

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
            message.attach_alternative(self.body_html, "text/html")
            message.send()
        self.recipient_count = len(emails)
        self.sent_at = timezone.now()
        self.save(update_fields=["recipient_count", "sent_at"])
        return len(emails)
