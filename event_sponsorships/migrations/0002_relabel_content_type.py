"""Relabel SponsorshipRequest's content type in place (issue #202).

sponsorships.sponsorshiprequest -> event_sponsorships.sponsorshiprequest, so
everything hanging off that django_content_type row stays attached: the
Executor group's four permissions (sponsorships 0003), checklist tasks and
notes, auditlog history. Running before post_migrate means Django never
creates a second, empty content type for the new label.

If a row with the target label already exists anyway (say post_migrate ran
from a half-applied deploy), every reference to it is moved onto the row
being relabelled first — permissions are merged by codename — and only then
is the duplicate deleted, so no CASCADE can take data with it. The reverse
migration does the same thing in the other direction.

The helpers are a copy of corporate_sponsorships 0001's, kept inline so this
migration never changes when that one does.
"""

from django.db import migrations, models

MODEL = "sponsorshiprequest"
OLD_APP = "sponsorships"
NEW_APP = "event_sponsorships"


def _unique_sets(model, field_name):
    """Field-name tuples that must stay unique and include `field_name`."""
    sets = [tuple(fields) for fields in model._meta.unique_together if field_name in fields]
    for constraint in model._meta.constraints:
        fields = getattr(constraint, "fields", ())
        if isinstance(constraint, models.UniqueConstraint) and fields and field_name in fields:
            sets.append(tuple(fields))
    return sets


def _repoint(model, field, from_pk, to_pk, using):
    """Move every `model` row whose `field` is `from_pk` to `to_pk`.

    A row that would collide with an existing one under a unique set is
    deleted instead: the surviving row already records the same fact (e.g.
    the same group holding the same permission).
    """
    manager = model._base_manager.db_manager(using)
    rows = manager.filter(**{field.attname: from_pk})
    unique_sets = _unique_sets(model, field.name)
    if not unique_sets:
        rows.update(**{field.attname: to_pk})
        return
    for row in rows:
        for fields in unique_sets:
            lookup = {}
            for name in fields:
                attname = model._meta.get_field(name).attname
                lookup[attname] = to_pk if name == field.name else getattr(row, attname)
            if manager.filter(**lookup).exists():
                row.delete()
                break
        else:
            manager.filter(pk=row.pk).update(**{field.attname: to_pk})


def _references_to(apps, target_label):
    """(model, field) for every concrete FK in the project state pointing at `target_label`."""
    for model in apps.get_models(include_auto_created=True):
        if model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.local_fields:
            if field.many_to_one and field.related_model._meta.label_lower == target_label:
                yield model, field


def _merge_content_types(apps, using, duplicate, keep):
    """Move everything referencing `duplicate` onto `keep`, then delete `duplicate`."""
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission._base_manager.db_manager(using)

    for perm in permissions.filter(content_type_id=duplicate.pk):
        survivor = permissions.filter(content_type_id=keep.pk, codename=perm.codename).first()
        if survivor is None:
            permissions.filter(pk=perm.pk).update(content_type_id=keep.pk)
            continue
        # Same permission on both rows: move group/user grants to the survivor.
        for model, field in _references_to(apps, "auth.permission"):
            _repoint(model, field, perm.pk, survivor.pk, using)
        perm.delete()

    for model, field in _references_to(apps, "contenttypes.contenttype"):
        if model is Permission:
            continue
        _repoint(model, field, duplicate.pk, keep.pk, using)

    # Nothing references it any more, so this cascades to nothing.
    duplicate.delete()


def _relabel(apps, schema_editor, from_app, to_app):
    ContentType = apps.get_model("contenttypes", "ContentType")
    using = schema_editor.connection.alias
    content_types = ContentType._base_manager.db_manager(using)

    source = content_types.filter(app_label=from_app, model=MODEL).first()
    if source is None:
        # Fresh database: post_migrate creates the content type under the
        # new label and nothing references the old one.
        return
    target = content_types.filter(app_label=to_app, model=MODEL).first()
    if target is not None:
        _merge_content_types(apps, using, duplicate=target, keep=source)

    source.app_label = to_app
    source.save(update_fields=["app_label"])
    ContentType.objects.clear_cache()


def relabel_forward(apps, schema_editor):
    _relabel(apps, schema_editor, OLD_APP, NEW_APP)


def relabel_backward(apps, schema_editor):
    _relabel(apps, schema_editor, NEW_APP, OLD_APP)


class Migration(migrations.Migration):

    dependencies = [
        ("event_sponsorships", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        # The relabel walks every FK to ContentType/Permission in the
        # historical state, so the apps holding them (checklist tasks and
        # notes, audit entries, per-user permission grants) must be in it.
        ("users", "0008_user_state_province"),
        ("checklists", "0003_task_assigned_to_task_due_date"),
        ("auditlog", "0017_add_actor_email"),
        # Executor's perms must exist before they are relabelled.
        ("sponsorships", "0003_executor_group"),
    ]

    operations = [
        migrations.RunPython(relabel_forward, relabel_backward),
    ]
