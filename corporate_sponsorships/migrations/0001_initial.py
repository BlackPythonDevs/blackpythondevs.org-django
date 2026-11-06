"""Move Sponsor from core into this app without touching its table (issue #201).

State only: the model keeps db_table="core_sponsor", so no table or row is
renamed and a deploy can briefly run new code against the old schema.
core 0017 deletes the old state copy of the model.

The django_content_type row is relabelled in place (core.sponsor ->
corporate_sponsorships.sponsor) so everything hanging off it stays attached:
the Executor group's four permissions, checklist tasks and notes, auditlog
history, Wagtail references. Running before post_migrate means Django never
creates a second, empty content type for the new label.

If a row with the target label already exists anyway (say post_migrate ran
from a half-applied deploy), every reference to it is moved onto the row
being relabelled first — permissions are merged by codename — and only then
is the duplicate deleted, so no CASCADE can take data with it. The reverse
migration does the same thing in the other direction.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MODEL = "sponsor"
OLD_APP = "core"
NEW_APP = "corporate_sponsorships"


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

    initial = True

    dependencies = [
        ("core", "0016_sponsor_primary_contact_user"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        # The relabel walks every FK to ContentType/Permission in the
        # historical state, so the apps holding them (checklist tasks and
        # notes, audit entries, per-user permission grants) must be in it.
        ("users", "0008_user_state_province"),
        ("checklists", "0003_task_assigned_to_task_due_date"),
        ("auditlog", "0017_add_actor_email"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Sponsor",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=120)),
                        ("url", models.URLField(blank=True)),
                        ("logo_static_path", models.CharField(blank=True, help_text="Fallback path under /static/ if no image has been uploaded, e.g. images/jetbrains.webp", max_length=255)),
                        ("sort_order", models.IntegerField(default=0)),
                        ("active", models.BooleanField(default=True)),
                        ("status", models.CharField(choices=[("active", "Active"), ("expiring_soon", "Expiring soon"), ("expired", "Expired"), ("cancelled", "Cancelled")], db_index=True, default="active", max_length=20)),
                        ("invoice_paid_date", models.DateField(blank=True, help_text="When Black Python Devs received payment. The sponsorship term runs one year from this date.", null=True)),
                        ("expires_at", models.DateField(blank=True, editable=False, null=True)),
                        ("contract_amount", models.DecimalField(blank=True, decimal_places=2, help_text="Contract value, for internal records. Never shown on the public site.", max_digits=10, null=True)),
                        ("primary_contact_name", models.CharField(blank=True, max_length=200)),
                        ("primary_contact_email", models.EmailField(blank=True, max_length=254)),
                        ("logo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="core.customimage")),
                        ("primary_contact_user", models.ForeignKey(blank=True, help_text="The member matching the primary contact email, if they have an account.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sponsored_for", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "core_sponsor",
                        "ordering": ["sort_order", "name"],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_backward),
    ]
