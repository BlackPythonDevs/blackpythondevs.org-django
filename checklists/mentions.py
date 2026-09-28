"""@username mentions in Note bodies (both the object-level notes list and
per-task comments — both are plain `Note` rows, see models.py).

Scoped to `permissions.assignable_users()` — the same pool a task can be
assigned to — so typing "@" can only ever reach someone who already has
`checklists.change_task` on this project, never an arbitrary member by
guessing their username. That keeps this generic app's notion of "who's
mentionable" consistent with its own "who's assignable" (views.py already
uses the same function for the assignee dropdown).
"""

import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from .permissions import assignable_users, display_label

MENTION_RE = re.compile(r"@(\w+)")


def _assignable_by_username():
    return {user.username: user for user in assignable_users()}


def find_mentioned_users(body):
    """Assignable users @mentioned in `body`, deduped, in first-seen order."""
    users_by_username = _assignable_by_username()
    mentioned = []
    for username in MENTION_RE.findall(body):
        user = users_by_username.get(username)
        if user is not None and user not in mentioned:
            mentioned.append(user)
    return mentioned


def render_mentions(body):
    """`body`, HTML-escaped, with @mentions of an assignable user highlighted.

    An "@word" that doesn't match an assignable user's username is left as
    plain escaped text — mentioning someone is opt-in to who's reachable,
    not a reason to reject "@" in ordinary writing.
    """
    users_by_username = _assignable_by_username()

    def replace(match):
        user = users_by_username.get(match.group(1))
        if user is None:
            return match.group(0)
        return format_html('<span class="checklist-mention" title="{}">{}</span>', display_label(user), match.group(0))

    return mark_safe(MENTION_RE.sub(replace, escape(body)))


def notify_mentioned_users(*, note, request, obj, app_label, model_name, task=None):
    """Email every user @mentioned in `note.body`, once, as a single bcc'd
    message (same synchronous, no-task-queue idiom as
    nominations.models.notify_onboarding_team and notifications.Notification.send).
    Never emails the author for mentioning themselves.
    """
    recipients = [user for user in find_mentioned_users(note.body) if user != note.created_by]
    if not recipients:
        return

    path = reverse(
        "checklists-detail", kwargs={"app_label": app_label, "model_name": model_name, "object_id": obj.pk}
    )
    where = f'on "{task.title}"' if task is not None else f"on {obj}"
    short_message = f"{display_label(note.created_by)} mentioned you {where}"

    emails = [user.email for user in recipients if user.email]
    if not emails:
        return
    message = EmailMultiAlternatives(
        subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}{short_message}",
        body=f'{display_label(note.created_by)} mentioned you in a comment {where}:\n\n'
        f'"{note.body}"\n\nView it: {request.build_absolute_uri(path)}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=emails,
    )
    message.send()
