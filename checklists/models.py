"""Generic follow-through tracking: a checklist of steps and a log of notes,
attachable to a record of any model via a `content_type`/`object_id` pair.

This app has no opinion about what it's attached to — see registry.py for how
another app wires a model in. `Task` and `Note` are deliberately separate:
a `Task` is a step that gets ticked off, a `Note` is free-form commentary
that's never "done". Both are manual, human-authored records — unrelated to
django-auditlog's automatic field-diff history (core/admin_auditlog.py),
which already tracks every model's raw changes.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class Task(models.Model):
    """One checklist step tracked against another model's record.

    `is_default` marks rows seeded from a registered template (see
    registry.py) so they're easy to tell apart from ad-hoc tasks an Executor
    added by hand.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)

    is_done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True, editable=False)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_checklist_tasks",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Keep done_at in step with is_done rather than trusting callers to
        # set both — toggling in the view only has to flip one field.
        if self.is_done and self.done_at is None:
            self.done_at = timezone.now()
        elif not self.is_done:
            self.done_at = None
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return bool(self.due_date and not self.is_done and self.due_date < timezone.localdate())


class Note(models.Model):
    """A free-form, timestamped note left against another model's record."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"Note on {self.content_type.name} #{self.object_id} ({self.created_at:%Y-%m-%d})"
