"""Sponsor moved from core into the corporate_sponsorships app (issue #201).

Covers the three things that move could break: the old /sponsors/ console
URLs (now permanent redirects, which must never leave the site), the
Executor group's permissions, and the records hanging off Sponsor's content
type (checklists, notes, audit history), which the migration relabels in
place rather than recreating.
"""

import pytest
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from checklists.models import Note, Task
from corporate_sponsorships.models import Sponsor

CODENAMES = {"view_sponsor", "add_sponsor", "change_sponsor", "delete_sponsor"}
NEW_PERMS = [f"corporate_sponsorships.{codename}" for codename in sorted(CODENAMES)]


class TestLegacyRedirect:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("/sponsors/", "/corporate-sponsors/"),
            ("/sponsors/new/", "/corporate-sponsors/new/"),
            ("/sponsors/12/", "/corporate-sponsors/12/"),
            ("/sponsors/12/edit/", "/corporate-sponsors/12/edit/"),
        ],
    )
    def test_old_paths_redirect_permanently_keeping_the_suffix(self, client, old, new):
        response = client.get(old)
        assert response.status_code == 301
        assert response["Location"] == new

    @pytest.mark.parametrize(
        "old", ["/sponsors//evil.example/", "/sponsors/\\evil.example/", "/sponsors///evil.example"]
    )
    def test_redirect_never_leaves_the_site(self, client, old):
        response = client.get(old)
        assert response.status_code == 301
        assert response["Location"].startswith("/corporate-sponsors/")
        assert response["Location"] == "/corporate-sponsors/" + old[len("/sponsors/") :].lstrip("/\\")

    def test_query_string_is_not_used_as_the_target(self, client):
        response = client.get("/sponsors/?next=https://evil.example/")
        assert response["Location"] == "/corporate-sponsors/"

    @pytest.mark.django_db
    def test_event_sponsorship_intake_is_not_shadowed(self, client):
        response = client.get("/event-sponsorships/request/")
        assert response.status_code == 200
        assert response.resolver_match.url_name == "event-sponsorship-request"


@pytest.mark.django_db
class TestPermissionsAfterMigrating:
    def test_no_content_type_is_left_under_the_old_label(self):
        assert not ContentType.objects.filter(app_label="core", model="sponsor").exists()
        assert ContentType.objects.get_for_model(Sponsor).app_label == "corporate_sponsorships"

    def test_executor_holds_exactly_the_four_new_perms(self):
        sponsor_perms = Group.objects.get(name="Executor").permissions.filter(codename__in=CODENAMES)
        assert set(sponsor_perms.values_list("content_type__app_label", "codename")) == {
            ("corporate_sponsorships", codename) for codename in CODENAMES
        }

    def test_executor_member_has_the_perms_and_a_groupless_user_has_none(self):
        User = get_user_model()
        executor = User.objects.create_user(username="exec", email="exec@example.com", password="pw")
        executor.groups.add(Group.objects.get(name="Executor"))
        nobody = User.objects.create_user(username="nobody", email="nobody@example.com", password="pw")

        assert executor.has_perms(NEW_PERMS)
        assert not any(User.objects.get(pk=nobody.pk).has_perm(perm) for perm in NEW_PERMS)

    def test_groupless_user_is_refused_and_anonymous_sent_to_login(self, client):
        nobody = get_user_model().objects.create_user(username="nobody", email="nobody@example.com", password="pw")
        response = client.get("/corporate-sponsors/")
        assert response.status_code == 302 and "/accounts/login/" in response["Location"]
        client.force_login(nobody)
        assert client.get("/corporate-sponsors/").status_code == 403


BEFORE = [("corporate_sponsorships", None)]
# The historical state to seed from once BEFORE is applied: core as it was
# just before the move.
BEFORE_STATE = [("core", "0016_sponsor_primary_contact_user")]
AFTER = [("corporate_sponsorships", "0001_initial"), ("core", "0017_move_sponsor_to_corporate_sponsorships")]


@pytest.fixture
def migrate(transactional_db):
    """Move corporate_sponsorships (and what depends on it) to `targets` and
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


def seed_old_sponsor(old_apps):
    """A Sponsor, under core's content type, with a checklist task, a note,
    an audit entry, and its four permissions granted to a group and a user."""
    from django.contrib.auth.management import create_permissions

    # The historical model, so the checklist post_save hook (which would
    # create a content type under the new label) doesn't fire.
    OldSponsor = old_apps.get_model("core", "Sponsor")
    sponsor = OldSponsor.objects.create(name="Acme Corp")

    core_config = old_apps.get_app_config("core")
    core_config.models_module = True
    create_permissions(core_config, apps=old_apps, verbosity=0)
    core_config.models_module = None

    content_type = ContentType.objects.get(app_label="core", model="sponsor")
    perms = Permission.objects.filter(content_type=content_type, codename__in=CODENAMES)
    assert perms.count() == 4

    group, _ = Group.objects.get_or_create(name="Executor")
    group.permissions.add(*perms)
    user = get_user_model().objects.create_user(username="direct", email="direct@example.com", password="pw")
    user.user_permissions.add(*perms)

    task = Task.objects.create(content_type=content_type, object_id=sponsor.pk, title="Contract sent")
    note = Note.objects.create(content_type=content_type, object_id=sponsor.pk, body="Called them")
    entry = LogEntry.objects.create(
        content_type=content_type, object_pk=str(sponsor.pk), object_repr="Acme Corp", action=0, changes={}
    )
    return {"sponsor": sponsor.pk, "ct": content_type.pk, "task": task.pk, "note": note.pk, "entry": entry.pk}


def assert_everything_follows_the_sponsor(ids):
    content_type = ContentType.objects.get_for_model(Sponsor)
    assert content_type.pk == ids["ct"], "the content type row was relabelled in place, not recreated"
    assert ContentType.objects.filter(model="sponsor", app_label__in=["core", "corporate_sponsorships"]).count() == 1

    sponsor = Sponsor.objects.get(pk=ids["sponsor"])
    assert Task.objects.get(pk=ids["task"]).content_object == sponsor
    assert Note.objects.get(pk=ids["note"]).content_object == sponsor
    assert LogEntry.objects.get(pk=ids["entry"]).content_type_id == content_type.pk

    group_perms = Group.objects.get(name="Executor").permissions.filter(codename__in=CODENAMES)
    assert set(group_perms.values_list("content_type__app_label", "codename")) == {
        ("corporate_sponsorships", codename) for codename in CODENAMES
    }
    assert get_user_model().objects.get(username="direct").has_perms(NEW_PERMS)
    nobody = get_user_model().objects.create_user(username="nobody", email="nobody@example.com", password="pw")
    assert not any(nobody.has_perm(perm) for perm in NEW_PERMS)


class TestContentTypeRelabel:
    def test_existing_records_stay_attached(self, migrate):
        ids = seed_old_sponsor(migrate(BEFORE, BEFORE_STATE))

        migrate(AFTER)

        assert_everything_follows_the_sponsor(ids)

    def test_a_preexisting_new_label_is_merged_without_losing_data(self, migrate):
        """post_migrate already made a (corporate_sponsorships, sponsor) row
        with its own permissions and a stray task: those are moved, not
        cascaded away, and the old row (with its id) is the one kept."""
        ids = seed_old_sponsor(migrate(BEFORE, BEFORE_STATE))
        duplicate = ContentType.objects.create(app_label="corporate_sponsorships", model="sponsor")
        stray_perm = Permission.objects.create(content_type=duplicate, codename="view_sponsor", name="Can view")
        extra_perm = Permission.objects.create(content_type=duplicate, codename="export_sponsor", name="Can export")
        Group.objects.get(name="Executor").permissions.add(stray_perm)
        stray_task = Task.objects.create(content_type=duplicate, object_id=ids["sponsor"], title="Logo added")

        migrate(AFTER)

        assert_everything_follows_the_sponsor(ids)
        assert not ContentType.objects.filter(pk=duplicate.pk).exists()
        assert not Permission.objects.filter(pk=stray_perm.pk).exists()
        assert Permission.objects.get(pk=extra_perm.pk).content_type_id == ids["ct"]
        assert Task.objects.get(pk=stray_task.pk).content_type_id == ids["ct"]

    def test_rollback_restores_the_core_label(self, migrate):
        ids = seed_old_sponsor(migrate(BEFORE, BEFORE_STATE))
        migrate(AFTER)

        migrate(BEFORE, BEFORE_STATE)

        content_type = ContentType.objects.get(pk=ids["ct"])
        assert (content_type.app_label, content_type.model) == ("core", "sponsor")
        assert set(
            Group.objects.get(name="Executor")
            .permissions.filter(codename__in=CODENAMES)
            .values_list("content_type__app_label", flat=True)
        ) == {"core"}
        assert Task.objects.get(pk=ids["task"]).content_type_id == ids["ct"]
