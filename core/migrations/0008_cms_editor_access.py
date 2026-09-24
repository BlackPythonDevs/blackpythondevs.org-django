"""Let Leadership Council, Leadership and Executor into the Wagtail admin (/cms).

Editor rights, deliberately without publish: they can log in, add and edit
pages anywhere in the tree and manage images and documents, but a superuser
publishes. Everything is added to the existing membership groups rather than a
new one, so granting someone a group in the admin is still the only step.

Only additive — reversing removes exactly what was added here.
"""

from django.db import migrations

from core.models import COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME

GROUP_NAMES = [COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME, "Executor"]
PAGE_CODENAMES = ["add_page", "change_page"]
COLLECTION_CODENAMES = {
    "core": ["add_customimage", "change_customimage", "choose_customimage"],
    "wagtaildocs": ["add_document", "change_document", "choose_document"],
}


def _ensure_permissions(apps):
    # Model permissions are normally created by a post_migrate signal that has
    # not fired yet mid-migration, so create them explicitly first.
    from django.contrib.auth.management import create_permissions

    for label in ("wagtailcore", "core", "wagtaildocs"):
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None


def _grants(apps):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    Page = apps.get_model("wagtailcore", "Page")
    Collection = apps.get_model("wagtailcore", "Collection")

    groups = Group.objects.filter(name__in=GROUP_NAMES)
    access_admin = Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
    page_perms = Permission.objects.filter(content_type__app_label="wagtailcore", codename__in=PAGE_CODENAMES)
    collection_perms = [
        p
        for label, codenames in COLLECTION_CODENAMES.items()
        for p in Permission.objects.filter(content_type__app_label=label, codename__in=codenames)
    ]
    root_page = Page.objects.filter(depth=1).first()
    root_collection = Collection.objects.filter(depth=1).first()
    return groups, access_admin, page_perms, collection_perms, root_page, root_collection


def grant(apps, schema_editor):
    _ensure_permissions(apps)
    GroupPagePermission = apps.get_model("wagtailcore", "GroupPagePermission")
    GroupCollectionPermission = apps.get_model("wagtailcore", "GroupCollectionPermission")
    groups, access_admin, page_perms, collection_perms, root_page, root_collection = _grants(apps)

    for group in groups:
        group.permissions.add(access_admin)
        if root_page:
            for perm in page_perms:
                GroupPagePermission.objects.get_or_create(group=group, page=root_page, permission=perm)
        if root_collection:
            for perm in collection_perms:
                GroupCollectionPermission.objects.get_or_create(
                    group=group, collection=root_collection, permission=perm
                )


def revoke(apps, schema_editor):
    GroupPagePermission = apps.get_model("wagtailcore", "GroupPagePermission")
    GroupCollectionPermission = apps.get_model("wagtailcore", "GroupCollectionPermission")
    groups, access_admin, page_perms, collection_perms, root_page, root_collection = _grants(apps)

    for group in groups:
        group.permissions.remove(access_admin)
        GroupPagePermission.objects.filter(group=group, page=root_page, permission__in=page_perms).delete()
        GroupCollectionPermission.objects.filter(
            group=group, collection=root_collection, permission__in=collection_perms
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_customimage_choose_permission"),
        ("sponsorships", "0003_executor_group"),
        ("wagtailadmin", "0001_create_admin_access_permissions"),
        ("wagtailcore", "0066_collection_management_permissions"),
        ("wagtaildocs", "0014_alter_document_file_size"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant, revoke),
    ]
