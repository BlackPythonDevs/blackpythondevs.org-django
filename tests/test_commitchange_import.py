"""The CommitChange payments export, aggregated and imported through admin."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.commitchange import CommitChangeError, aggregate_payments
from core.models import FoundationalSupport
from core.supporters import (
    SUPPORTER_EMAIL_DOMAIN,
    diff_roster,
    find_name_conflicts,
    get_or_create_supporter_user,
    import_supporters,
    is_placeholder,
)

HEADER = "Date,Full Name,Email,Gross Amount,Anonymous?"


def payments(*rows):
    return "\n".join([HEADER, *(",".join(str(cell) for cell in row) for row in rows)])


class TestAggregation:
    """Payments become one record per person per year, over the threshold."""

    def test_a_year_of_giving_is_summed(self):
        rows, summary = aggregate_payments(
            payments(
                ("2024-01-01", "Grace Hopper", "grace@example.com", "$120.00", "False"),
                ("2024-06-01", "Grace Hopper", "grace@example.com", "$80.00", "False"),
            )
        )
        assert [(row["name"], row["year"], row["total"]) for row in rows] == [
            ("Grace Hopper", "2024", Decimal("200.00"))
        ]
        assert summary["supporters"] == 1

    def test_giving_under_the_threshold_is_dropped(self):
        rows, summary = aggregate_payments(
            payments(("2024-01-01", "Ada Lovelace", "ada@example.com", "$199.99", "False"))
        )
        assert rows == []
        assert summary["below_threshold"] == 1

    def test_the_threshold_is_configurable(self):
        text = payments(("2024-01-01", "Ada Lovelace", "ada@example.com", "$50.00", "False"))
        assert aggregate_payments(text, threshold=Decimal("25"))[0]

    def test_anonymous_payments_never_count(self):
        """Not just hidden — an anonymous gift cannot push someone over."""
        rows, summary = aggregate_payments(
            payments(
                ("2024-01-01", "Ada Lovelace", "ada@example.com", "$150.00", "True"),
                ("2024-02-01", "Ada Lovelace", "ada@example.com", "$100.00", "False"),
            )
        )
        assert rows == []
        assert summary["anonymous_skipped"] == 1

    def test_years_are_kept_apart(self):
        rows, _ = aggregate_payments(
            payments(
                ("2023-12-31", "Grace Hopper", "grace@example.com", "$250.00", "False"),
                ("2024-01-01", "Grace Hopper", "grace@example.com", "$250.00", "False"),
            )
        )
        assert [row["year"] for row in rows] == ["2024", "2023"]

    def test_one_email_is_one_person_however_the_name_is_typed(self):
        rows, _ = aggregate_payments(
            payments(
                ("2024-01-01", "GRACE HOPPER", "grace@example.com", "$100.00", "False"),
                ("2024-02-01", "Grace Hopper", "grace@example.com", "$100.00", "False"),
            )
        )
        assert len(rows) == 1
        # The shouted spelling came first but is tidied, not preserved.
        assert rows[0]["name"] == "Grace Hopper"

    def test_refunds_subtract(self):
        rows, _ = aggregate_payments(
            payments(
                ("2024-01-01", "Ada Lovelace", "ada@example.com", "$250.00", "False"),
                ("2024-02-01", "Ada Lovelace", "ada@example.com", "($100.00)", "False"),
            )
        )
        assert rows == []

    def test_header_aliases_and_missing_columns(self):
        text = "date,name,amount\n01/15/2024,Ada Lovelace,300\n"
        rows, summary = aggregate_payments(text)
        assert rows[0]["year"] == "2024" and rows[0]["email"] == ""
        assert not summary["has_email_column"] and not summary["has_anonymous_column"]

        with pytest.raises(CommitChangeError, match="a name"):
            aggregate_payments("date,amount\n2024-01-01,300\n")

    def test_unreadable_values_are_reported(self):
        with pytest.raises(CommitChangeError, match="as a date"):
            aggregate_payments(payments(("last tuesday", "Ada", "ada@example.com", "$300", "False")))
        with pytest.raises(CommitChangeError, match="as an amount"):
            aggregate_payments(payments(("2024-01-01", "Ada", "ada@example.com", "lots", "False")))


class TestDiff:
    """The preview has to agree with what the import will actually do."""

    pytestmark = pytest.mark.django_db

    def test_existing_support_is_not_counted_as_new(self, db):
        User = get_user_model()
        user = User.objects.create_user(username="grace", email="grace@example.com", display_name="Grace Hopper")
        FoundationalSupport.objects.create(user=user, year=2024)

        diff = diff_roster(
            [
                {"name": "Grace Hopper", "email": "grace@example.com", "year": "2024"},
                {"name": "Grace Hopper", "email": "grace@example.com", "year": "2025"},
            ]
        )
        assert [row["year"] for row in diff["unchanged"]] == ["2024"]
        assert [row["year"] for row in diff["added"]] == ["2025"]
        assert diff["removed"] == []

    def test_records_the_export_omits_are_flagged(self, db):
        User = get_user_model()
        user = User.objects.create_user(username="ada", email="ada@example.com", display_name="Ada Lovelace")
        FoundationalSupport.objects.create(user=user, year=2019)

        diff = diff_roster([{"name": "Grace Hopper", "email": "grace@example.com", "year": "2024"}])
        assert [support.year for support in diff["removed"]] == [2019]

    def test_a_placeholder_account_matches_on_name(self, db):
        """Someone imported from the old fixture must not be duplicated."""
        user, _ = get_or_create_supporter_user(get_user_model(), "Grace Hopper")
        FoundationalSupport.objects.create(user=user, year=2024)

        diff = diff_roster([{"name": "Grace Hopper", "email": "grace@example.com", "year": "2024"}])
        assert len(diff["unchanged"]) == 1


class TestNameConflicts:
    """A name shared with a claimed account is a question, not a guess."""

    pytestmark = pytest.mark.django_db

    @pytest.fixture
    def claimed(self, db):
        return get_user_model().objects.create_user(
            username="grace", email="grace@navy.example", display_name="Grace Hopper"
        )

    def row(self, email="grace@work.example"):
        return {"name": "Grace Hopper", "email": email, "year": "2024"}

    def test_a_claimed_namesake_is_flagged(self, claimed):
        conflicts = find_name_conflicts([self.row()])
        assert len(conflicts) == 1
        assert conflicts[0]["candidates"] == [claimed]
        # Left to itself the import makes a second account, so that is the default.
        assert conflicts[0]["default"] == "separate"

    def test_a_matching_email_is_not_a_conflict(self, claimed):
        assert find_name_conflicts([self.row(email="grace@navy.example")]) == []

    def test_placeholders_alone_are_not_conflicts(self, db):
        """Otherwise a full re-upload would ask about the whole roster."""
        get_or_create_supporter_user(get_user_model(), "Grace Hopper")
        assert find_name_conflicts([self.row()]) == []

    def test_a_row_with_no_email_still_conflicts(self, claimed):
        assert len(find_name_conflicts([self.row(email="")])) == 1

    def test_the_diff_agrees_with_what_the_import_does(self, claimed):
        """The bug this guards: the preview must not claim a merge it won't do."""
        FoundationalSupport.objects.create(user=claimed, year=2024)
        rows = [self.row()]

        diff = diff_roster(rows)
        assert diff["unchanged"] == [] and len(diff["added"]) == 1

        import_supporters(rows)
        assert get_user_model().objects.filter(display_name="Grace Hopper").count() == 2

    def test_linking_puts_support_on_the_chosen_account(self, claimed):
        import_supporters([{**self.row(), "user_id": claimed.pk}])

        assert claimed.foundational_support.get().year == 2024
        claimed.refresh_from_db()
        # Their own address is theirs; the export does not get to change it.
        assert claimed.email == "grace@navy.example"
        assert get_user_model().objects.filter(display_name="Grace Hopper").count() == 1

    def test_separate_refuses_even_a_placeholder(self, db):
        User = get_user_model()
        placeholder, _ = get_or_create_supporter_user(User, "Grace Hopper")

        import_supporters([{**self.row(), "separate": True}])

        placeholder.refresh_from_db()
        assert is_placeholder(placeholder)
        assert User.objects.filter(email="grace@work.example").exists()


class TestAdminImport:
    """Uploading previews; only the confirming POST writes."""

    pytestmark = pytest.mark.django_db

    @pytest.fixture
    def staff_client(self, client, db):
        User = get_user_model()
        admin = User.objects.create_superuser(username="boss", email="boss@example.com", password="pw")
        client.force_login(admin)
        return client

    @pytest.fixture
    def export(self, tmp_path):
        def write(text):
            path = tmp_path / "payments.csv"
            path.write_text(text)
            return path.open("rb")

        return write

    def url(self):
        return reverse("admin:core_foundationalsupport_import")

    def test_the_changelist_links_to_the_importer(self, staff_client):
        html = staff_client.get(reverse("admin:core_foundationalsupport_changelist")).content.decode()
        assert self.url() in html

    def test_upload_previews_without_writing(self, staff_client, export):
        response = staff_client.post(
            self.url(),
            {
                "csv_file": export(payments(("2024-01-01", "Grace Hopper", "grace@example.com", "$300", "False"))),
                "threshold": "200",
            },
        )
        assert response.status_code == 200
        assert "Grace Hopper" in response.content.decode()
        assert not FoundationalSupport.objects.exists()

    def test_confirming_imports_the_previewed_roster(self, staff_client, export):
        staff_client.post(
            self.url(),
            {
                "csv_file": export(payments(("2024-01-01", "Grace Hopper", "grace@example.com", "$300", "False"))),
                "threshold": "200",
            },
        )
        response = staff_client.post(self.url(), {"confirm": "1"}, follow=True)
        assert response.status_code == 200

        support = FoundationalSupport.objects.get()
        assert support.year == 2024
        assert support.user.email == "grace@example.com"
        assert support.status == FoundationalSupport.LISTED

    def test_confirming_twice_does_not_re_import(self, staff_client, export):
        staff_client.post(
            self.url(),
            {
                "csv_file": export(payments(("2024-01-01", "Grace Hopper", "grace@example.com", "$300", "False"))),
                "threshold": "200",
            },
        )
        staff_client.post(self.url(), {"confirm": "1"})
        response = staff_client.post(self.url(), {"confirm": "1"}, follow=True)
        assert "expired" in response.content.decode()
        assert FoundationalSupport.objects.count() == 1

    def test_replace_clears_what_the_export_omits(self, staff_client, export):
        stale, _ = get_or_create_supporter_user(get_user_model(), "Someone Else")
        FoundationalSupport.objects.create(user=stale, year=2019)

        staff_client.post(
            self.url(),
            {
                "csv_file": export(payments(("2024-01-01", "Grace Hopper", "grace@example.com", "$300", "False"))),
                "threshold": "200",
                "replace": "on",
            },
        )
        staff_client.post(self.url(), {"confirm": "1"})

        assert [s.year for s in FoundationalSupport.objects.all()] == [2024]
        assert not get_user_model().objects.filter(email__endswith=f"@{SUPPORTER_EMAIL_DOMAIN}").exists()

    def test_a_broken_export_is_reported_not_raised(self, staff_client, export):
        response = staff_client.post(
            self.url(),
            {"csv_file": export("date,amount\n2024-01-01,300\n"), "threshold": "200"},
        )
        assert response.status_code == 200
        assert "needs a name" in response.content.decode()

    def test_an_export_with_nobody_over_the_threshold_is_rejected(self, staff_client, export):
        response = staff_client.post(
            self.url(),
            {
                "csv_file": export(payments(("2024-01-01", "Grace Hopper", "grace@example.com", "$5", "False"))),
                "threshold": "200",
            },
        )
        assert "No one in that export reached the threshold." in response.content.decode()

    def upload(self, staff_client, export, csv=None, **extra):
        csv = csv or payments(("2024-01-01", "Grace Hopper", "grace@work.example", "$300", "False"))
        return staff_client.post(self.url(), {"csv_file": export(csv), "threshold": "200", **extra})

    def test_a_clash_with_a_claimed_account_is_put_to_the_user(self, staff_client, export):
        User = get_user_model()
        claimed = User.objects.create_user(username="grace", email="grace@navy.example", display_name="Grace Hopper")
        html = self.upload(staff_client, export).content.decode()
        assert "Is this the same person?" in html
        assert f'value="link:{claimed.pk}"' in html

    def test_answering_same_person_merges_onto_that_account(self, staff_client, export):
        User = get_user_model()
        claimed = User.objects.create_user(username="grace", email="grace@navy.example", display_name="Grace Hopper")
        self.upload(staff_client, export)
        staff_client.post(self.url(), {"confirm": "1", "resolve_0": f"link:{claimed.pk}"})

        assert claimed.foundational_support.get().year == 2024
        assert User.objects.filter(display_name="Grace Hopper").count() == 1

    def test_answering_different_person_keeps_them_apart(self, staff_client, export):
        User = get_user_model()
        User.objects.create_user(username="grace", email="grace@navy.example", display_name="Grace Hopper")
        self.upload(staff_client, export)
        staff_client.post(self.url(), {"confirm": "1", "resolve_0": "separate"})

        assert User.objects.filter(display_name="Grace Hopper").count() == 2
        assert FoundationalSupport.objects.get().user.email == "grace@work.example"

    def test_a_skipped_row_is_not_imported(self, staff_client, export):
        get_user_model().objects.create_user(username="grace", email="grace@navy.example", display_name="Grace Hopper")
        self.upload(staff_client, export)
        response = staff_client.post(self.url(), {"confirm": "1", "resolve_0": "skip"}, follow=True)

        assert not FoundationalSupport.objects.exists()
        assert "1 row left out at your request." in response.content.decode()

    def test_an_account_that_was_never_offered_cannot_be_chosen(self, staff_client, export):
        """A hand-edited form must not be able to attach support to any member."""
        User = get_user_model()
        User.objects.create_user(username="grace", email="grace@navy.example", display_name="Grace Hopper")
        bystander = User.objects.create_user(username="nobody", email="nobody@example.com")

        self.upload(staff_client, export)
        staff_client.post(self.url(), {"confirm": "1", "resolve_0": f"link:{bystander.pk}"})

        assert not bystander.foundational_support.exists()
        assert FoundationalSupport.objects.get().user.email == "grace@work.example"

    def test_rows_with_no_clash_need_no_answer(self, staff_client, export):
        self.upload(staff_client, export)
        staff_client.post(self.url(), {"confirm": "1"})
        assert FoundationalSupport.objects.count() == 1

    def test_non_staff_cannot_reach_it(self, client, db):
        get_user_model().objects.create_user(username="member", email="m@example.com", password="pw")
        client.login(username="member", password="pw")
        response = client.get(self.url())
        assert response.status_code == 302 and "login" in response["Location"]
