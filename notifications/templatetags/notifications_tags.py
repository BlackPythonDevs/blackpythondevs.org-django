"""{% notification_bell %}: the unread-count indicator in the site header
(templates/includes/header.html), linking to the signed-in member's own
inbox (notifications:inbox). Renders nothing for an anonymous visitor.
"""

from django import template

from ..models import UserNotification

register = template.Library()


@register.inclusion_tag("notifications/includes/bell.html", takes_context=True)
def notification_bell(context):
    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return {"authenticated": False}
    unread_count = UserNotification.objects.filter(recipient=request.user, read_at__isnull=True).count()
    return {"authenticated": True, "unread_count": unread_count}
