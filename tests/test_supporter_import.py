"""The foundational-supporters roster import command.

The roster is re-uploaded wholesale; emails make accounts claimable. These
tests need no pages at all — just the database — so they use the plain `db`
fixture rather than a site.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import FoundationalSupport
from core.supporters import SUPPORTER_EMAIL_DOMAIN, get_or_create_supporter_user, is_placeholder

pytestmark = pytest.mark.django_db


@pytest.fixture
def roster(tmp_path):
    def write(rows, suffix=".csv"):
        path = tmp_path / f"supporters{suffix}"
        if suffix == ".csv":
            lines = ["name,email,year,status"]
            lines += [",".join(str(cell) for cell in row) for row in rows]
            path.write_text("\n".join(lines))
        else:
            path.write_text(json.dumps(rows))
        return path

    return write


def test_import_with_emails_creates_claimable_accounts(db, roster):
    path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
    call_command("import_foundational_supporters", str(path), verbosity=0)

    user = get_user_model().objects.get(email="grace@example.com")
    assert user.display_name == "Grace Hopper"
    assert not is_placeholder(user)
    assert user.foundational_support.get().year == 2023


def test_email_upgrades_the_existing_placeholder(db, roster):
    User = get_user_model()
    placeholder, _ = get_or_create_supporter_user(User, "Grace Hopper")
    FoundationalSupport.objects.create(user=placeholder, year=2022)

    path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
    call_command("import_foundational_supporters", str(path), verbosity=0)

    placeholder.refresh_from_db()
    assert placeholder.email == "grace@example.com"
    assert User.objects.filter(display_name="Grace Hopper").count() == 1
    # The pre-existing year came along rather than being stranded.
    assert set(placeholder.foundational_support.values_list("year", flat=True)) == {2022, 2023}


def test_replace_swaps_the_roster_and_clears_placeholders(db, roster):
    User = get_user_model()
    # Seed an existing roster entry so --replace has something to swap out.
    placeholder, _ = get_or_create_supporter_user(User, "Old Roster Name")
    FoundationalSupport.objects.create(user=placeholder, year=2020)

    path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
    call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

    assert FoundationalSupport.objects.count() == 1
    assert not User.objects.filter(email__endswith=f"@{SUPPORTER_EMAIL_DOMAIN}").exists()


def test_replace_keeps_real_accounts(db, roster):
    User = get_user_model()
    member = User.objects.create_user(username="member", email="member@example.com")

    path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
    call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

    assert User.objects.filter(pk=member.pk).exists()


def test_year_keyed_json_is_accepted(db, roster):
    path = roster({"2021": ["Bare Name", {"name": "Grace Hopper", "email": "grace@example.com"}]}, ".json")
    call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

    assert set(FoundationalSupport.objects.values_list("year", flat=True)) == {2021}
    assert get_user_model().objects.filter(display_name="Bare Name").exists()


def test_a_bad_row_aborts_the_whole_import(db, roster):
    User = get_user_model()
    # Seed an existing roster entry so the aborted import must leave it intact.
    placeholder, _ = get_or_create_supporter_user(User, "Old Roster Name")
    FoundationalSupport.objects.create(user=placeholder, year=2020)

    path = roster([("Grace Hopper", "grace@example.com", "not-a-year", "listed")])

    with pytest.raises(CommandError):
        call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

    assert set(FoundationalSupport.objects.values_list("user__display_name", flat=True)) == {"Old Roster Name"}


def test_dry_run_writes_nothing(db, roster):
    User = get_user_model()
    # Seed an existing roster entry so the dry run must leave it intact.
    placeholder, _ = get_or_create_supporter_user(User, "Old Roster Name")
    FoundationalSupport.objects.create(user=placeholder, year=2020)

    path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
    call_command("import_foundational_supporters", str(path), "--replace", "--dry-run", verbosity=0)
    assert set(FoundationalSupport.objects.values_list("user__display_name", flat=True)) == {"Old Roster Name"}
