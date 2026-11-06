"""The sponsorships app was renamed to event_sponsorships (issue #202).

Covers what that rename could break: the old /sponsorships/ URLs (now
permanent redirects, which must never leave the site), the Executor group's
permissions, and the records hanging off SponsorshipRequest's content type
(checklists, notes, audit history), which the migration relabels in place
rather than recreating.
"""

import datetime

import pytest
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from checklists.models import Note, Task
from event_sponsorships.models import SponsorshipRequest

CODENAMES = {
    "view_sponsorshiprequest",
    "add_sponsorshiprequest",
    "change_sponsorshiprequest",
    "delete_sponsorshiprequest",
}
NEW_PERMS = [f"event_sponsorships.{codename}" for codename in sorted(CODENAMES)]


class TestLegacyRedirect:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("/sponsorships/", "/event-sponsorships/"),
            ("/sponsorships/new/", "/event-sponsorships/new/"),
            ("/sponsorships/12/", "/event-sponsorships/12/"),
            ("/sponsorships/12/edit/", "/event-sponsorships/12/edit/"),
            ("/sponsorships/12/delete/", "/event-sponsorships/12/delete/"),
            ("/sponsorships/request/", "/event-sponsorships/request/"),
            ("/sponsorships/request/thanks/", "/event-sponsorships/request/thanks/"),
        ],
    )
    def test_old_paths_redirect_permanently_keeping_the_suffix(self, client, old, new):
        response = client.get(old)
        assert response.status_code == 301
        assert response["Location"] == new

    @pytest.mark.parametrize(
        "old",
        [
            "/sponsorships//evil.example/",
            "/sponsorships/%2F%2Fevil.example/",
            "/sponsorships/\\evil.example/",
            "/sponsorships///evil.example",
            "/sponsorships/%5Cevil.example/",
        ],
    )
    def test_redirect_never_leaves_the_site(self, client, old):
        response = client.get(old)
        assert response.status_code == 301
        location = response["Location"]
        assert location.startswith("/event-sponsorships/")
        assert not location.startswith("//")
        assert location.startswith("/event-sponsorships/evil.example")

    def test_query_string_is_kept_as_a_query_string(self, client):
        response = client.get("/sponsorships/?status=completed&year=2025")
        assert response["Location"] == "/event-sponsorships/?status=completed&year=2025"

    def test_query_string_never_becomes_the_target(self, client):
        response = client.get("/sponsorships/?next=https://evil.example/")
        assert response["Location"].startswith("/event-sponsorships/?")

    @pytest.mark.django_db
    def test_new_paths_are_served(self, client):
        response = client.get("/event-sponsorships/request/")
        assert response.status_code == 200
        assert response.resolver_match.url_name == "event-sponsorship-request"
        assert client.get("/event-sponsorships/request/thanks/").status_code == 200


@pytest.mark.django_db
class TestPermissionsAfterMigrating:
    def test_no_content_type_is_left_under_the_old_label(self):
        assert not ContentType.objects.filter(app_label="sponsorships", model="sponsorshiprequest").exists()
        assert ContentType.objects.get_for_model(SponsorshipRequest).app_label == "event_sponsorships"

    def test_table_name_is_unchanged(self):
        assert SponsorshipRequest._meta.db_table == "sponsorships_sponsorshiprequest"

    def test_executor_holds_exactly_the_four_new_perms(self):
        perms = Group.objects.get(name="Executor").permissions.filter(codename__in=CODENAMES)
        assert set(perms.values_list("content_type__app_label", "codename")) == {
            ("event_sponsorships", codename) for codename in CODENAMES
        }

    def test_console_stays_executor_only(self, client):
        User = get_user_model()
        executor = User.objects.create_user(username="exec", email="exec@example.com", password="pw")
        executor.groups.add(Group.objects.get(name="Executor"))
        nobody = User.objects.create_user(username="nobody", email="nobody@example.com", password="pw")

        response = client.get("/event-sponsorships/")
        assert response.status_code == 302 and "/accounts/login/" in response["Location"]
        client.force_login(nobody)
        assert client.get("/event-sponsorships/").status_code == 403
        client.force_login(executor)
        assert client.get("/event-sponsorships/").status_code == 200


BEFORE = [("event_sponsorships", None)]
# The historical state to seed from once BEFORE is applied: sponsorships as
# it was just before the rename.
BEFORE_STATE = [("sponsorships", "0006_sponsorshiprequest_contact_email_and_more")]
AFTER = [("event_sponsorships", "0002_relabel_content_type"), ("sponsorships", "0007_delete_sponsorshiprequest_state")]


@pytest.fixture
def migrate(transactional_db):
    """Move event_sponsorships (and what depends on it) to `targets` and
    return that point's historical apps. Back to the latest state afterwards."""

    def run(targets, state=None):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        ContentType.objects.clear_cache()
        return MigrationExecutor(connection).loader.project_state(state or targets).apps

    yield run
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    ContentType.objects.clear_cache()


def seed_old_request(old_apps):
    """A SponsorshipRequest under the old content type, with a checklist task,
    a note, an audit entry, and its four permissions granted to Executor and a user."""
    from django.contrib.auth.management import create_permissions

    # The historical model, so the checklist post_save hook (which would
    # create a content type under the new label) doesn't fire.
    OldRequest = old_apps.get_model("sponsorships", "SponsorshipRequest")
    request = OldRequest.objects.create(
        name="PyCon Ghana", year=2025, country="GH", start_date=datetime.date(2025, 8, 1)
    )

    config = old_apps.get_app_config("sponsorships")
    config.models_module = True
    create_permissions(config, apps=old_apps, verbosity=0)
    config.models_module = None

    content_type = ContentType.objects.get(app_label="sponsorships", model="sponsorshiprequest")
    perms = Permission.objects.filter(content_type=content_type, codename__in=CODENAMES)
    assert perms.count() == 4

    group, _ = Group.objects.get_or_create(name="Executor")
    group.permissions.add(*perms)
    user = get_user_model().objects.create_user(username="direct", email="direct@example.com", password="pw")
    user.user_permissions.add(*perms)

    task = Task.objects.create(content_type=content_type, object_id=request.pk, title="Approved")
    note = Note.objects.create(content_type=content_type, object_id=request.pk, body="Emailed the organisers")
    entry = LogEntry.objects.create(
        content_type=content_type, object_pk=str(request.pk), object_repr="PyCon Ghana", action=0, changes={}
    )
    return {"request": request.pk, "ct": content_type.pk, "task": task.pk, "note": note.pk, "entry": entry.pk}


def assert_everything_follows_the_request(ids):
    content_type = ContentType.objects.get_for_model(SponsorshipRequest)
    assert content_type.pk == ids["ct"], "the content type row was relabelled in place, not recreated"
    assert (
        ContentType.objects.filter(
            model="sponsorshiprequest", app_label__in=["sponsorships", "event_sponsorships"]
        ).count()
        == 1
    )

    request = SponsorshipRequest.objects.get(pk=ids["request"])
    assert Task.objects.get(pk=ids["task"]).content_object == request
    assert Note.objects.get(pk=ids["note"]).content_object == request
    assert LogEntry.objects.get(pk=ids["entry"]).content_type_id == content_type.pk

    group_perms = Group.objects.get(name="Executor").permissions.filter(codename__in=CODENAMES)
    assert set(group_perms.values_list("content_type__app_label", "codename")) == {
        ("event_sponsorships", codename) for codename in CODENAMES
    }
    assert get_user_model().objects.get(username="direct").has_perms(NEW_PERMS)
    nobody = get_user_model().objects.create_user(username="nobody", email="nobody@example.com", password="pw")
    assert not any(nobody.has_perm(perm) for perm in NEW_PERMS)


class TestContentTypeRelabel:
    def test_existing_records_stay_attached(self, migrate):
        ids = seed_old_request(migrate(BEFORE, BEFORE_STATE))

        migrate(AFTER)

        assert_everything_follows_the_request(ids)
        # The existing checklist is found under the new label (the page at
        # /checklists/event_sponsorships/... is covered in test_checklists.py;
        # a transactional test can't render it once the site rows are flushed).
        from checklists import registry

        assert registry.get_definition("event_sponsorships.sponsorshiprequest") is not None
        assert Task.objects.filter(
            content_type__app_label="event_sponsorships", object_id=ids["request"], title="Approved"
        ).exists()

    def test_a_preexisting_new_label_is_merged_without_losing_data(self, migrate):
        ids = seed_old_request(migrate(BEFORE, BEFORE_STATE))
        duplicate = ContentType.objects.create(app_label="event_sponsorships", model="sponsorshiprequest")
        stray_perm = Permission.objects.create(
            content_type=duplicate, codename="view_sponsorshiprequest", name="Can view"
        )
        Group.objects.get(name="Executor").permissions.add(stray_perm)
        stray_task = Task.objects.create(content_type=duplicate, object_id=ids["request"], title="Event completed")

        migrate(AFTER)

        assert_everything_follows_the_request(ids)
        assert not ContentType.objects.filter(pk=duplicate.pk).exists()
        assert not Permission.objects.filter(pk=stray_perm.pk).exists()
        assert Task.objects.get(pk=stray_task.pk).content_type_id == ids["ct"]

    def test_rollback_restores_the_old_label_and_reapplies(self, migrate):
        ids = seed_old_request(migrate(BEFORE, BEFORE_STATE))
        migrate(AFTER)

        migrate(BEFORE, BEFORE_STATE)

        content_type = ContentType.objects.get(pk=ids["ct"])
        assert (content_type.app_label, content_type.model) == ("sponsorships", "sponsorshiprequest")
        assert set(
            Group.objects.get(name="Executor")
            .permissions.filter(codename__in=CODENAMES)
            .values_list("content_type__app_label", flat=True)
        ) == {"sponsorships"}

        migrate(AFTER)

        assert_everything_follows_the_request(ids)
