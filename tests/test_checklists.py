"""The generic checklist/notes app, exercised through its two real consumers:
core.Sponsor (registered in core/apps.py's ready()) and
sponsorships.SponsorshipRequest (sponsorships/apps.py's ready()), the latter
also used to test embedding {% checklist_widget %} into an existing
neapolitan console page.

Access control mirrors tests/test_sponsorships.py: the front-end console
requires the full Task+Note permission set, so only the Executor group and
superusers get in.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management.base import CommandError

from checklists import registry
from checklists.management.commands.backfill_checklists import Command as BackfillCommand
from checklists.management.commands.create_test_executors import TEST_EXECUTORS
from checklists.management.commands.create_test_executors import Command as CreateTestExecutorsCommand
from checklists.mentions import find_mentioned_users, render_mentions
from checklists.models import Note, Task
from checklists.permissions import display_label
from core.models import Sponsor
from sponsorships.models import SponsorshipRequest

pytestmark = pytest.mark.django_db

SPONSOR_STEPS = [
    "Contract sent",
    "Contract signed",
    "Invoice sent",
    "Invoice paid",
    "Logo added",
    "Announcement posted",
    "Thank-you sent",
]

SPONSORSHIP_REQUEST_STEPS = [
    "Prospectus reviewed",
    "Approved",
    "Funds transferred",
    "Event completed",
    "Added to public events page",
]


@pytest.fixture
def sponsor(db):
    return Sponsor.objects.create(name="Acme Corp")


@pytest.fixture
def executor(db):
    user = get_user_model().objects.create_user(username="exec", email="exec@example.com", password="pw")
    user.groups.add(Group.objects.get(name="Executor"))
    return user


@pytest.fixture
def other_executor(db):
    user = get_user_model().objects.create_user(username="exec2", email="exec2@example.com", password="pw")
    user.groups.add(Group.objects.get(name="Executor"))
    return user


@pytest.fixture
def member(db):
    return get_user_model().objects.create_user(username="member", email="member@example.com", password="pw")


@pytest.fixture
def sponsorship_request(db):
    return SponsorshipRequest.objects.create(
        name="PyCon Somewhere", start_date=datetime.date(2026, 5, 1), country="NG"
    )


def sponsor_urls(sponsor):
    return [
        "/checklists/",
        "/checklists/core/sponsor/",
        f"/checklists/core/sponsor/{sponsor.pk}/",
    ]


class TestRegistration:
    def test_creating_sponsor_seeds_default_checklist(self, sponsor):
        content_type = ContentType.objects.get_for_model(Sponsor)
        titles = list(
            Task.objects.filter(content_type=content_type, object_id=sponsor.pk).order_by("order").values_list(
                "title", flat=True
            )
        )
        assert titles == SPONSOR_STEPS
        assert all(task.is_default for task in Task.objects.filter(content_type=content_type, object_id=sponsor.pk))

    def test_seeding_is_idempotent(self, sponsor):
        registry.seed_defaults(sponsor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        assert Task.objects.filter(content_type=content_type, object_id=sponsor.pk).count() == len(SPONSOR_STEPS)


class TestConsoleAccess:
    @pytest.mark.parametrize(
        "login_as,expected_status",
        [("executor", 200), (None, 302), ("member", 403)],
        ids=["executor", "anonymous", "ordinary_member"],
    )
    def test_console_access_by_role(self, request, client, sponsor, login_as, expected_status):
        if login_as:
            client.force_login(request.getfixturevalue(login_as))
        for url in sponsor_urls(sponsor):
            assert client.get(url).status_code == expected_status, url


class TestChecklistActions:
    def test_toggle_task_sets_and_clears_done_fields(self, client, executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "toggle", "task_id": task.pk})
        task.refresh_from_db()
        assert task.is_done is True
        assert task.done_at is not None
        assert task.done_by == executor

        client.post(url, {"action": "toggle", "task_id": task.pk})
        task.refresh_from_db()
        assert task.is_done is False
        assert task.done_at is None
        assert task.done_by is None

    def test_add_task_creates_a_custom_task(self, client, executor, sponsor):
        client.force_login(executor)
        client.post(f"/checklists/core/sponsor/{sponsor.pk}/", {"action": "add_task", "title": "Send swag"})

        content_type = ContentType.objects.get_for_model(Sponsor)
        custom = Task.objects.get(content_type=content_type, object_id=sponsor.pk, title="Send swag")
        assert custom.is_default is False

    def test_add_note_records_author(self, client, executor, sponsor):
        client.force_login(executor)
        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "add_note", "body": "Called them, following up next week."})

        content_type = ContentType.objects.get_for_model(Sponsor)
        note = Note.objects.get(content_type=content_type, object_id=sponsor.pk)
        assert note.created_by == executor
        assert note.body == "Called them, following up next week."


class TestDisplayLabel:
    """Wherever the checklists app shows a person (assignee, done_by, comment/
    note author, mention highlight/notification text), it prefers `@username`
    — what you'd actually type to mention them — over the site-wide
    `User.__str__` default (display_name/full name/email)."""

    def test_prefers_username_over_email(self, executor):
        assert display_label(executor) == executor.username
        assert display_label(executor) != executor.email

    def test_falls_back_to_display_name_when_username_is_blank(self, executor):
        executor.username = ""
        executor.display_name = "Executor Person"
        assert display_label(executor) == "Executor Person"

    def test_none_returns_empty_string(self):
        assert display_label(None) == ""


class TestTaskAssignment:
    """Clicking a task (the <details> in widget.html) reveals a due-date and
    assignee editor. "Assignable" is deliberately not "the Executor group" by
    name — see checklists/permissions.py — but in this project that group is
    exactly who holds checklists.change_task, so it should resolve to the
    same people in practice."""

    def test_assignable_users_are_executors_not_ordinary_members(self, executor, member):
        from checklists.permissions import assignable_users

        users = list(assignable_users())
        assert executor in users
        assert member not in users

    def test_update_task_details_sets_due_date_and_assignee(self, client, executor, other_executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(
            url,
            {
                "action": "update_task_details",
                "task_id": task.pk,
                "due_date": "2026-05-01",
                "assigned_to": other_executor.pk,
            },
        )

        task.refresh_from_db()
        assert task.due_date == datetime.date(2026, 5, 1)
        assert task.assigned_to == other_executor

    def test_update_task_details_clears_fields_when_blank(self, client, executor, other_executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()
        task.due_date = datetime.date(2026, 5, 1)
        task.assigned_to = other_executor
        task.save()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "update_task_details", "task_id": task.pk, "due_date": "", "assigned_to": ""})

        task.refresh_from_db()
        assert task.due_date is None
        assert task.assigned_to is None

    def test_assigning_to_a_non_executor_is_ignored(self, client, executor, member, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(
            url, {"action": "update_task_details", "task_id": task.pk, "due_date": "", "assigned_to": member.pk}
        )

        task.refresh_from_db()
        assert task.assigned_to is None

    def test_assignee_dropdown_lists_executors_on_the_sponsor_page(self, client, executor, member, sponsor):
        client.force_login(executor)
        content = client.get(f"/sponsors/{sponsor.pk}/").content.decode()
        assert executor.username in content
        assert f'value="{member.pk}"' not in content


class TestTaskComments:
    """Per-task comments (widget.html's per-task <details>) reuse Note's own
    generic relation, just pointed at the Task itself instead of at the
    checklist's own object — see views.py's add_task_comment branch."""

    def test_add_task_comment_creates_a_note_on_the_task(self, client, executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "add_task_comment", "task_id": task.pk, "body": "Following up Monday."})

        task_content_type = ContentType.objects.get_for_model(Task)
        comment = Note.objects.get(content_type=task_content_type, object_id=task.pk)
        assert comment.body == "Following up Monday."
        assert comment.created_by == executor

    def test_task_comment_renders_under_its_own_task_in_the_widget(self, client, executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        tasks = list(Task.objects.filter(content_type=content_type, object_id=sponsor.pk).order_by("order"))
        first_task, second_task = tasks[0], tasks[1]

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "add_task_comment", "task_id": first_task.pk, "body": "Comment on task one"})

        content = client.get(url).content.decode()
        first_index = content.index(first_task.title)
        second_index = content.index(second_task.title)
        comment_index = content.index("Comment on task one")
        assert first_index < comment_index < second_index

    def test_commenting_on_a_task_from_another_object_404s(self, client, executor, sponsor, sponsorship_request):
        client.force_login(executor)
        other_content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        foreign_task = Task.objects.filter(
            content_type=other_content_type, object_id=sponsorship_request.pk
        ).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        response = client.post(url, {"action": "add_task_comment", "task_id": foreign_task.pk, "body": "Nope"})

        assert response.status_code == 404


class TestMentions:
    """"@username" in a note or task comment body (mentions.py) — scoped to
    assignable_users(), the same pool as the assignee dropdown, so a mention
    can only ever reach someone already allowed to act on this checklist."""

    def test_render_mentions_highlights_an_assignable_users_username(self, executor):
        html = render_mentions(f"cc @{executor.username} on this")
        assert 'class="checklist-mention"' in html
        assert f"@{executor.username}" in html

    def test_render_mentions_leaves_an_unmatched_mention_as_plain_text(self, executor, member):
        html = render_mentions(f"cc @{member.username} and @not_a_real_user")
        assert "checklist-mention" not in html
        assert f"@{member.username}" in html
        assert "@not_a_real_user" in html

    def test_render_mentions_escapes_html_in_the_body(self):
        html = render_mentions("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_find_mentioned_users_dedupes_and_skips_non_assignable(self, executor, other_executor, member):
        body = f"@{executor.username} @{member.username} @{executor.username} @{other_executor.username}"
        assert find_mentioned_users(body) == [executor, other_executor]

    def test_add_note_with_mention_emails_the_mentioned_executor(self, client, executor, other_executor, sponsor):
        client.force_login(executor)
        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "add_note", "body": f"@{other_executor.username} can you take this one?"})

        assert len(mail.outbox) == 1
        assert mail.outbox[0].bcc == [other_executor.email]
        assert "mentioned you" in mail.outbox[0].subject

    def test_add_task_comment_with_mention_emails_the_mentioned_executor(
        self, client, executor, other_executor, sponsor
    ):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(
            url,
            {"action": "add_task_comment", "task_id": task.pk, "body": f"@{other_executor.username} thoughts?"},
        )

        assert len(mail.outbox) == 1
        assert mail.outbox[0].bcc == [other_executor.email]
        assert task.title in mail.outbox[0].subject or task.title in mail.outbox[0].body

    def test_mentioning_yourself_does_not_send_an_email(self, client, executor, sponsor):
        client.force_login(executor)
        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "add_note", "body": f"@{executor.username} note to self"})

        assert len(mail.outbox) == 0

    def test_mentioning_a_non_assignable_member_does_not_send_an_email(self, client, executor, member, sponsor):
        client.force_login(executor)
        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "add_note", "body": f"@{member.username} fyi"})

        assert len(mail.outbox) == 0


class TestMentionSuggestions:
    """The "@" autocomplete's backing endpoint (MentionSuggestionsView),
    queried live as someone types (see static/js/checklist-mentions.js)."""

    def test_matches_by_username_prefix(self, client, executor, other_executor):
        client.force_login(executor)
        response = client.get("/checklists/mentions/", {"q": other_executor.username[:4]})

        assert response.status_code == 200
        usernames = [row["username"] for row in response.json()]
        assert other_executor.username in usernames
        assert executor.username in usernames  # "exec" is a prefix of both fixtures' usernames

    def test_excludes_non_assignable_users(self, client, executor, member):
        client.force_login(executor)
        response = client.get("/checklists/mentions/", {"q": member.username})

        usernames = [row["username"] for row in response.json()]
        assert member.username not in usernames

    def test_empty_query_still_returns_assignable_users(self, client, executor):
        client.force_login(executor)
        response = client.get("/checklists/mentions/")

        usernames = [row["username"] for row in response.json()]
        assert executor.username in usernames

    def test_anonymous_is_redirected(self, client):
        response = client.get("/checklists/mentions/")
        assert response.status_code == 302

    def test_ordinary_member_is_forbidden(self, client, member):
        client.force_login(member)
        response = client.get("/checklists/mentions/")
        assert response.status_code == 403


class TestHtmxPartialUpdates:
    """An `HX-Request` header (sent automatically by htmx.min.js on every
    hx-post) makes the view hand back just the widget's own markup instead
    of redirecting — see views.py's ChecklistDetailView.post(). Without that
    header (e.g. a form submit with JS disabled) the existing redirect
    behavior, covered by TestChecklistActions, is unchanged."""

    def test_toggle_via_htmx_returns_the_widget_partial_instead_of_redirecting(self, client, executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        task = Task.objects.filter(content_type=content_type, object_id=sponsor.pk).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        response = client.post(url, {"action": "toggle", "task_id": task.pk}, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        assert "checklist-widget" in content
        assert f"<s>{task.title}</s>" in content
        task.refresh_from_db()
        assert task.is_done is True

    def test_add_task_via_htmx_shows_the_new_task_in_the_returned_partial(self, client, executor, sponsor):
        client.force_login(executor)
        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        response = client.post(url, {"action": "add_task", "title": "Send swag"}, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert "Send swag" in response.content.decode()


class TestReorder:
    def test_reorder_updates_task_order(self, client, executor, sponsor):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(Sponsor)
        tasks = list(Task.objects.filter(content_type=content_type, object_id=sponsor.pk).order_by("order"))
        new_order = list(reversed(tasks))

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(url, {"action": "reorder", "task_id": [str(task.pk) for task in new_order]})

        reordered_titles = list(
            Task.objects.filter(content_type=content_type, object_id=sponsor.pk).order_by("order").values_list(
                "title", flat=True
            )
        )
        assert reordered_titles == [task.title for task in new_order]

    def test_reorder_ignores_a_task_id_from_another_object(self, client, executor, sponsor, sponsorship_request):
        client.force_login(executor)
        sponsor_content_type = ContentType.objects.get_for_model(Sponsor)
        other_content_type = ContentType.objects.get_for_model(SponsorshipRequest)

        sponsor_tasks = list(
            Task.objects.filter(content_type=sponsor_content_type, object_id=sponsor.pk).order_by("order")
        )
        foreign_task = Task.objects.filter(
            content_type=other_content_type, object_id=sponsorship_request.pk
        ).first()

        url = f"/checklists/core/sponsor/{sponsor.pk}/"
        client.post(
            url,
            {
                "action": "reorder",
                "task_id": [str(foreign_task.pk)] + [str(task.pk) for task in reversed(sponsor_tasks)],
            },
        )

        foreign_task.refresh_from_db()
        assert foreign_task.order == 0

        reordered_titles = list(
            Task.objects.filter(content_type=sponsor_content_type, object_id=sponsor.pk).order_by(
                "order"
            ).values_list("title", flat=True)
        )
        assert reordered_titles == [task.title for task in reversed(sponsor_tasks)]


class TestWidgetEmbedding:
    """{% checklist_widget %} embedded in sponsorships' own neapolitan detail page."""

    def test_creating_sponsorship_request_seeds_its_own_checklist(self, sponsorship_request):
        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        titles = list(
            Task.objects.filter(content_type=content_type, object_id=sponsorship_request.pk)
            .order_by("order")
            .values_list("title", flat=True)
        )
        assert titles == SPONSORSHIP_REQUEST_STEPS

    def test_widget_renders_on_the_neapolitan_detail_page(self, client, executor, sponsorship_request):
        client.force_login(executor)
        response = client.get(f"/sponsorships/{sponsorship_request.pk}/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Event sponsorship checklist" in content
        assert "Prospectus reviewed" in content

    def test_toggling_from_the_widget_redirects_back_to_the_embedding_page(
        self, client, executor, sponsorship_request
    ):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        task = Task.objects.filter(content_type=content_type, object_id=sponsorship_request.pk).first()

        detail_url = f"/sponsorships/{sponsorship_request.pk}/"
        checklist_url = f"/checklists/sponsorships/sponsorshiprequest/{sponsorship_request.pk}/"
        response = client.post(checklist_url, {"action": "toggle", "task_id": task.pk, "next": detail_url})

        assert response.status_code == 302
        assert response.url == detail_url
        task.refresh_from_db()
        assert task.is_done is True

    def test_unsafe_next_falls_back_to_the_checklists_own_detail_page(
        self, client, executor, sponsorship_request
    ):
        client.force_login(executor)
        content_type = ContentType.objects.get_for_model(SponsorshipRequest)
        task = Task.objects.filter(content_type=content_type, object_id=sponsorship_request.pk).first()

        checklist_url = f"/checklists/sponsorships/sponsorshiprequest/{sponsorship_request.pk}/"
        response = client.post(
            checklist_url, {"action": "toggle", "task_id": task.pk, "next": "http://evil.example.com/steal"}
        )

        assert response.url == checklist_url


class TestCreateTestExecutorsCommand:
    """Django's test runner forces DEBUG off regardless of the settings
    module (see django.test.utils.setup_test_environment), so every test
    here passes force=True except the one that means to exercise the guard
    itself."""

    def test_creates_accounts_in_the_executor_group(self):
        CreateTestExecutorsCommand().handle(force=True)

        group = Group.objects.get(name="Executor")
        for username, _email in TEST_EXECUTORS:
            user = get_user_model().objects.get(username=username)
            assert group in user.groups.all()

    def test_is_idempotent(self):
        CreateTestExecutorsCommand().handle(force=True)
        CreateTestExecutorsCommand().handle(force=True)

        assert get_user_model().objects.filter(username=TEST_EXECUTORS[0][0]).count() == 1

    def test_refuses_to_run_outside_debug_without_force(self, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError):
            CreateTestExecutorsCommand().handle(force=False)

    def test_force_overrides_the_debug_guard(self, settings):
        settings.DEBUG = False
        CreateTestExecutorsCommand().handle(force=True)
        assert get_user_model().objects.filter(username=TEST_EXECUTORS[0][0]).exists()


class TestBackfillCommand:
    def test_backfills_rows_that_predate_registration(self):
        # bulk_create bypasses save()/post_save, so this sponsor gets no tasks
        # from the signal — exactly the "predates registration" case.
        sponsor = Sponsor.objects.bulk_create([Sponsor(name="Legacy Sponsor")])[0]
        content_type = ContentType.objects.get_for_model(Sponsor)
        assert not Task.objects.filter(content_type=content_type, object_id=sponsor.pk).exists()

        BackfillCommand().handle(dry_run=False)

        assert Task.objects.filter(content_type=content_type, object_id=sponsor.pk).count() == len(SPONSOR_STEPS)
