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

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.utils import timezone

from communities.models import Community
from core.models import LEADERSHIP_GROUP_NAME
from users.models import User


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
