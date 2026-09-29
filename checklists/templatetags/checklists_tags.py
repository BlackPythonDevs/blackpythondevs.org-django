"""Template tags for embedding the checklists app into another page's
template (e.g. a neapolitan console's own detail page).

{% checklist_widget object %} embeds the tasks/notes checklist itself. Its
forms post straight to the checklists app's own endpoint
(views.ChecklistDetailView), carrying the embedding page's URL as `next` so
the action redirects back to wherever it was embedded rather than to the
checklists app's own detail page. Access is still enforced independently by
that endpoint's own permission_required — embedding a widget on a page never
widens who can act on it.

Per-task comments reuse the same generic `Note` model as the object-level
notes list, just pointed at the `Task` itself (content_type=Task,
object_id=task.pk) instead of at `obj` — no separate model needed since Note
was already generic. Each task gets its own matching comments attached as
`task.comments` (a plain Python attribute, not a DB field) so widget.html can
read `task.comments` directly rather than needing a "look this up in a dict
by key" template filter.

{{ note.body|mentionify }} (mentions.py) highlights any "@username" in a
note/comment body that matches an assignable user, and is what actually sends
the "you were mentioned" email — see views.py's add_note/add_task_comment
branches, which call notify_mentioned_users() right after creating the Note.

{% task_activity object %} is separate and optional: it surfaces the
django-auditlog history (who ticked/added/renamed a task and when) for
`object`'s own tasks, as its own section on the page rather than folded into
the widget — a page can show the checklist without it, or place it wherever
makes sense on the page. It stays scoped to just this object's own Task rows,
unlike the django-admin audit log, which is superuser-only precisely because
it can read *any* tracked model's history (see core/admin_auditlog.py) —
this exposes nothing a viewer couldn't already see by acting on those same
tasks.
"""

from auditlog.models import LogEntry
from django import template
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from .. import registry
from ..mentions import render_mentions
from ..models import Note, Task
from ..permissions import assignable_users, display_label

register = template.Library()
register.filter("mentionify", render_mentions)
register.filter("checklist_person", display_label)


@register.inclusion_tag("checklists/includes/widget.html", takes_context=True)
def checklist_widget(context, obj):
    definition = registry.get_definition(obj._meta.label_lower)
    if definition is None:
        return {"registered": False}

    content_type = ContentType.objects.get_for_model(obj)
    request = context.get("request")

    tasks = list(Task.objects.filter(content_type=content_type, object_id=obj.pk))
    task_content_type = ContentType.objects.get_for_model(Task)
    comments_by_task_id = {}
    for comment in Note.objects.filter(
        content_type=task_content_type, object_id__in=[task.pk for task in tasks]
    ).order_by("created_at"):
        comments_by_task_id.setdefault(comment.object_id, []).append(comment)
    for task in tasks:
        task.comments = comments_by_task_id.get(task.pk, [])

    return {
        "registered": True,
        "process_name": definition["name"],
        "tasks": tasks,
        "notes": Note.objects.filter(content_type=content_type, object_id=obj.pk),
        "assignable_users": assignable_users(),
        "post_url": reverse(
            "checklists-detail",
            kwargs={
                "app_label": content_type.app_label,
                "model_name": content_type.model,
                "object_id": obj.pk,
            },
        ),
        "next": request.path if request else "",
    }


@register.inclusion_tag("checklists/includes/link.html")
def checklist_link(obj):
    """A checklist glyph linking to `obj`'s checklist page; renders nothing if
    `obj`'s model has no registered checklist."""
    if registry.get_definition(obj._meta.label_lower) is None:
        return {"url": None}
    content_type = ContentType.objects.get_for_model(obj)
    return {
        "url": reverse(
            "checklists-detail",
            kwargs={
                "app_label": content_type.app_label,
                "model_name": content_type.model,
                "object_id": obj.pk,
            },
        )
    }


@register.inclusion_tag("checklists/includes/task_activity.html")
def task_activity(obj):
    content_type = ContentType.objects.get_for_model(obj)
    task_ids = Task.objects.filter(content_type=content_type, object_id=obj.pk).values_list("pk", flat=True)
    task_content_type = ContentType.objects.get_for_model(Task)
    return {
        "task_activity": LogEntry.objects.filter(
            content_type=task_content_type, object_id__in=list(task_ids)
        ).select_related("actor"),
    }
