"""Registry other apps use to attach a default checklist to their own models.

Mirrors how django-auditlog (already a dependency here) is wired up
per-model: the *owning* app calls `register()` from its own
`apps.py.ready()`, passing the model class directly. This app never imports
the models it tracks, so adding a checklist to another process later — a
SponsorshipRequest, a nomination, whatever needs one next — is one call from
that app's own `ready()`, with no change here.

    # core/apps.py
    def ready(self):
        from checklists.registry import register
        from .models import Sponsor
        register(Sponsor, ["Contract sent", "Contract signed", ...])
"""

from django.db.models.signals import post_save

_registry = {}


def register(model, steps, *, name=None):
    """Give `model` a default checklist of `steps` (ordered titles).

    Connects a post_save receiver scoped to `model` that seeds the steps as
    Task rows the first time an instance is created. Idempotent: an instance
    that already has tasks (e.g. re-saved, or backfilled) is left alone.
    """
    label = model._meta.label_lower
    _registry[label] = {"model": model, "steps": list(steps), "name": name or str(model._meta.verbose_name)}
    post_save.connect(_seed_defaults, sender=model, weak=False, dispatch_uid=f"checklists.seed.{label}")


def get_definition(label):
    """The registration entry for "<app_label>.<model_name>", or None."""
    return _registry.get(label)


def definitions():
    """Every registered {"model", "steps", "name"}, for the process index."""
    return list(_registry.values())


def _seed_defaults(sender, instance, created, **kwargs):
    if not created:
        return
    seed_defaults(instance)


def seed_defaults(instance):
    """Create the default Task rows for `instance` if it has none yet.

    Public (not just the post_save hook) so the backfill command can call it
    directly for rows that predate registration.
    """
    from django.contrib.contenttypes.models import ContentType

    from .models import Task

    definition = _registry.get(instance._meta.label_lower)
    if not definition:
        return

    content_type = ContentType.objects.get_for_model(instance)
    if Task.objects.filter(content_type=content_type, object_id=instance.pk).exists():
        return

    Task.objects.bulk_create(
        Task(content_type=content_type, object_id=instance.pk, title=title, is_default=True, order=order)
        for order, title in enumerate(definition["steps"])
    )
