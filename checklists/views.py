"""Front-end portal for the generic checklist/notes app.

Entirely driven by registry.py — nothing here names a specific model. Access
follows the same reasoning as sponsorships.views.SponsorshipRequestView:
requiring the full add/change/delete/view set on both Task and Note keeps
this a management console for users who can do everything with it (in
practice, the Executor group and superusers), not a partial view for anyone
else.
"""

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView, View

from . import registry
from .mentions import notify_mentioned_users
from .models import Note, Task
from .permissions import assignable_users, display_label

PERMISSION_REQUIRED = [
    "checklists.view_task",
    "checklists.add_task",
    "checklists.change_task",
    "checklists.delete_task",
    "checklists.view_note",
    "checklists.add_note",
]


def _task_progress(content_type, object_ids):
    """{object_id: (done, total)} for every object_id that has at least one task."""
    rows = (
        Task.objects.filter(content_type=content_type, object_id__in=object_ids)
        .values("object_id")
        .annotate(total=Count("id"), done=Count("id", filter=Q(is_done=True)))
    )
    return {row["object_id"]: (row["done"], row["total"]) for row in rows}


class ChecklistsAccessMixin(PermissionRequiredMixin):
    permission_required = PERMISSION_REQUIRED


def _get_definition_or_404(app_label, model_name):
    definition = registry.get_definition(f"{app_label}.{model_name}")
    if definition is None:
        raise Http404(f"No checklist is registered for {app_label}.{model_name}.")
    return definition


class ProcessIndexView(ChecklistsAccessMixin, TemplateView):
    """Every registered process type, with how many of its objects are fully checked off."""

    template_name = "checklists/process_index.html"

    def get_context_data(self, **kwargs):
        processes = []
        for definition in registry.definitions():
            model = definition["model"]
            content_type = ContentType.objects.get_for_model(model)
            object_ids = list(model._default_manager.values_list("pk", flat=True))
            progress = _task_progress(content_type, object_ids)
            fully_done = sum(1 for done, total in progress.values() if total and done == total)
            processes.append(
                {
                    "app_label": content_type.app_label,
                    "model_name": content_type.model,
                    "name": definition["name"],
                    "total": len(object_ids),
                    "fully_done": fully_done,
                }
            )
        return {**super().get_context_data(**kwargs), "processes": processes}


class ProcessObjectListView(ChecklistsAccessMixin, TemplateView):
    """Every object of one registered process type, each with its own progress."""

    template_name = "checklists/object_list.html"

    def get_context_data(self, **kwargs):
        definition = _get_definition_or_404(kwargs["app_label"], kwargs["model_name"])
        model = definition["model"]
        content_type = ContentType.objects.get_for_model(model)
        objects = list(model._default_manager.all())
        progress = _task_progress(content_type, [obj.pk for obj in objects])

        rows = [
            {
                "object": obj,
                "done": progress.get(obj.pk, (0, 0))[0],
                "total": progress.get(obj.pk, (0, 0))[1],
            }
            for obj in objects
        ]
        return {
            **super().get_context_data(**kwargs),
            "process_name": definition["name"],
            "app_label": content_type.app_label,
            "model_name": content_type.model,
            "rows": rows,
        }


class MentionSuggestionsView(ChecklistsAccessMixin, View):
    """JSON backing for the "@" autocomplete in widget.html's comment/note
    textareas (static/js/checklist-mentions.js): matches assignable_users()
    (mentions.py's own mentionable pool) by a `?q=` prefix against `username`
    and `email` only — the two fields every Django user model has, since this
    app stays generic and can't assume a project-specific field like a
    display name exists.
    """

    def get(self, request):
        query = request.GET.get("q", "").strip()
        users = assignable_users()
        if query:
            users = users.filter(Q(username__istartswith=query) | Q(email__istartswith=query))
        results = [{"username": user.username, "label": display_label(user)} for user in users[:8]]
        return JsonResponse(results, safe=False)


class ChecklistDetailView(ChecklistsAccessMixin, View):
    """One object's tasks and notes, with actions to toggle/add both."""

    def _load(self, app_label, model_name, object_id):
        definition = _get_definition_or_404(app_label, model_name)
        obj = get_object_or_404(definition["model"], pk=object_id)
        content_type = ContentType.objects.get_for_model(definition["model"])
        return definition, obj, content_type

    def get(self, request, app_label, model_name, object_id):
        definition, obj, _content_type = self._load(app_label, model_name, object_id)
        context = {
            "process_name": definition["name"],
            "app_label": app_label,
            "model_name": model_name,
            "object": obj,
        }
        return TemplateResponse(request, "checklists/checklist_detail.html", context)

    def post(self, request, app_label, model_name, object_id):
        definition, obj, content_type = self._load(app_label, model_name, object_id)
        action = request.POST.get("action")

        if action == "toggle":
            task = get_object_or_404(Task, pk=request.POST.get("task_id"), content_type=content_type, object_id=obj.pk)
            task.is_done = not task.is_done
            task.done_by = request.user if task.is_done else None
            task.save()
        elif action == "add_task":
            title = request.POST.get("title", "").strip()
            if title:
                last_order = (
                    Task.objects.filter(content_type=content_type, object_id=obj.pk)
                    .order_by("-order")
                    .values_list("order", flat=True)
                    .first()
                    or 0
                )
                Task.objects.create(
                    content_type=content_type, object_id=obj.pk, title=title, order=last_order + 1
                )
        elif action == "add_note":
            body = request.POST.get("body", "").strip()
            if body:
                note = Note.objects.create(
                    content_type=content_type, object_id=obj.pk, body=body, created_by=request.user
                )
                notify_mentioned_users(note=note, request=request, obj=obj, app_label=app_label, model_name=model_name)
        elif action == "update_task_details":
            task = get_object_or_404(Task, pk=request.POST.get("task_id"), content_type=content_type, object_id=obj.pk)

            raw_due_date = request.POST.get("due_date", "").strip()
            if not raw_due_date:
                task.due_date = None
            else:
                parsed_due_date = parse_date(raw_due_date)
                if parsed_due_date is not None:
                    task.due_date = parsed_due_date

            assigned_to_id = request.POST.get("assigned_to", "").strip()
            if not assigned_to_id:
                task.assigned_to = None
            else:
                # A tampered id for someone without checklists.change_task
                # (not in assignable_users()) unassigns rather than errors —
                # same "silently drop bad input" behavior as an empty title
                # on add_task above.
                task.assigned_to = assignable_users().filter(pk=assigned_to_id).first()

            task.save()
        elif action == "add_task_comment":
            task = get_object_or_404(Task, pk=request.POST.get("task_id"), content_type=content_type, object_id=obj.pk)
            body = request.POST.get("body", "").strip()
            if body:
                # Reuses Note's own generic relation, just pointed at the
                # Task itself rather than at `obj` — see checklists_tags.py's
                # checklist_widget() for how these get matched back up to
                # their task for display.
                note = Note.objects.create(
                    content_type=ContentType.objects.get_for_model(Task),
                    object_id=task.pk,
                    body=body,
                    created_by=request.user,
                )
                notify_mentioned_users(
                    note=note, request=request, obj=obj, app_label=app_label, model_name=model_name, task=task
                )
        elif action == "reorder":
            # The client sends every task_id in its new order (see
            # static/js/checklist-dragdrop.js); scoping the lookup to this
            # object's own tasks keeps a tampered id for some other object's
            # task from being reachable here.
            ordered_ids = [int(pk) for pk in request.POST.getlist("task_id") if pk.isdigit()]
            tasks_by_id = {
                task.pk: task
                for task in Task.objects.filter(pk__in=ordered_ids, content_type=content_type, object_id=obj.pk)
            }
            updated = []
            for position, task_id in enumerate(ordered_ids):
                task = tasks_by_id.get(task_id)
                if task is not None:
                    task.order = position
                    updated.append(task)
            Task.objects.bulk_update(updated, ["order"])

        if request.headers.get("HX-Request") == "true":
            # htmx already has this page open — hand back just the widget's
            # own markup (fresh tasks/notes/order) for it to swap in place,
            # instead of a redirect it would otherwise have to follow.
            from .templatetags.checklists_tags import checklist_widget

            context = checklist_widget({"request": request}, obj)
            return TemplateResponse(request, "checklists/includes/widget.html", context)

        return redirect(self._redirect_target(request, app_label, model_name, obj.pk))

    def _redirect_target(self, request, app_label, model_name, object_id):
        # `next` lets a widget embedded on another page (e.g. a neapolitan
        # console's own detail page) send its user back there instead of to
        # this app's own detail page.
        next_url = request.POST.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return next_url
        return reverse(
            "checklists-detail", kwargs={"app_label": app_label, "model_name": model_name, "object_id": object_id}
        )
