import datetime
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from blog.models import BlogIndexPage, BlogPage
from core.models import Author, FoundationalSupport, Leader, Sponsor
from core.supporters import SUPPORTER_EMAIL_DOMAIN, get_or_create_supporter_user, is_placeholder
from events.models import EventIndexPage
from home.models import AboutPage, StandardPage, SupportPage

pytestmark = pytest.mark.django_db


@pytest.fixture
def site(bootstrapped_site):
    """This whole file is about what `bootstrap_site` seeds, so it needs the real thing."""
    return bootstrapped_site


def test_bootstrap_creates_page_tree(site):
    assert site.slug == "home"
    assert AboutPage.objects.count() == 1
    assert BlogIndexPage.objects.count() == 1
    assert EventIndexPage.objects.count() == 1
    assert SupportPage.objects.count() == 1
    assert StandardPage.objects.filter(slug="code-of-conduct").exists()


def test_bootstrap_is_idempotent(site):
    from django.core.management import call_command
    from wagtail.models import Page

    before = Page.objects.count()
    call_command("bootstrap_site", verbosity=0)
    assert Page.objects.count() == before


def test_bootstrap_seeds_snippets(site):
    assert Sponsor.objects.filter(active=True).exists()
    assert Leader.objects.filter(role=Leader.EXECUTOR).exists()
    assert Leader.objects.filter(role=Leader.COUNCIL).exists()
    assert Author.objects.exists()


def test_principles_heading_is_not_double_escaped(site):
    """The seed copy must hold a literal '&', not a pre-escaped entity."""
    headings = [
        card["heading"]
        for block in site.body
        if block.block_type == "card_grid"
        for card in block.value["cards"]
    ]
    assert "Community & Belonging" in headings
    assert not any("&amp;" in h for h in headings)


@pytest.mark.parametrize(
    "path",
    ["/", "/about/", "/news/", "/events/", "/support/", "/code-of-conduct/"],
)
def test_pages_render(client, site, path):
    assert client.get(path).status_code == 200


def test_home_page_renders_ampersand_correctly(client, site):
    html = client.get("/").content.decode()
    assert "Community &amp; Belonging" in html
    assert "&amp;amp;" not in html


class TestBlog:
    @pytest.fixture
    def post(self, site):
        index = BlogIndexPage.objects.get()
        author = Author.objects.create(name="Test Author", bio="A bio.")
        page = BlogPage(
            title="Hello World",
            slug="hello-world",
            date=datetime.date(2026, 1, 1),
            description="A test post.",
            body=[("paragraph", "<p>Body copy.</p>")],
        )
        index.add_child(instance=page)
        page.save_revision().publish()
        page.authors.add(author)
        page.save()
        return page

    def test_post_renders(self, client, post):
        response = client.get(post.url)
        assert response.status_code == 200
        html = response.content.decode()
        assert "Hello World" in html
        assert "Test Author" in html
        assert "A bio." in html

    def test_post_appears_in_index(self, client, post):
        html = client.get("/news/").content.decode()
        assert "Hello World" in html

    def test_index_pagination_does_not_break_on_bad_page(self, client, post):
        assert client.get("/news/?page=not-a-number").status_code == 200
        assert client.get("/news/?page=9999").status_code == 200

    def test_tag_filter(self, client, post):
        post.tags.add("community")
        post.save_revision().publish()
        assert "Hello World" in client.get("/news/?tag=community").content.decode()
        assert "Hello World" not in client.get("/news/?tag=missing").content.decode()


class TestFoundationalSupport:
    """Supporters are user accounts; the page lists only public support."""

    def test_bootstrap_creates_unverified_supporter_accounts(self, site):
        support = FoundationalSupport.objects.select_related("user").first()
        assert support is not None
        user = support.user
        assert user.display_name
        assert user.email.endswith(f"@{SUPPORTER_EMAIL_DOMAIN}")
        assert not user.has_usable_password()

    def test_repeat_support_reuses_one_account(self, site):
        User = get_user_model()
        years = {2024, 2025}
        user, created = get_or_create_supporter_user(User, "Grace Hopper")
        assert created
        for year in years:
            FoundationalSupport.objects.create(user=user, year=year)

        again, created = get_or_create_supporter_user(User, "Grace Hopper")
        assert not created and again.pk == user.pk
        assert set(user.foundational_support.values_list("year", flat=True)) == years

    def test_only_listed_support_is_published(self, client, site):
        User = get_user_model()
        public, _ = get_or_create_supporter_user(User, "Listed Person")
        private, _ = get_or_create_supporter_user(User, "Private Person")
        FoundationalSupport.objects.create(user=public, year=2026)
        FoundationalSupport.objects.create(
            user=private, year=2026, status=FoundationalSupport.ANONYMOUS
        )

        html = client.get("/support/").content.decode()
        assert "Listed Person" in html
        assert "Private Person" not in html


class TestSupporterImport:
    """The roster is re-uploaded wholesale; emails make accounts claimable."""

    @pytest.fixture
    def roster(self, tmp_path):
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

    def test_import_with_emails_creates_claimable_accounts(self, site, roster):
        path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
        call_command("import_foundational_supporters", str(path), verbosity=0)

        user = get_user_model().objects.get(email="grace@example.com")
        assert user.display_name == "Grace Hopper"
        assert not is_placeholder(user)
        assert user.foundational_support.get().year == 2023

    def test_email_upgrades_the_existing_placeholder(self, site, roster):
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

    def test_replace_swaps_the_roster_and_clears_placeholders(self, site, roster):
        User = get_user_model()
        before = FoundationalSupport.objects.count()
        assert before > 0

        path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
        call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

        assert FoundationalSupport.objects.count() == 1
        assert not User.objects.filter(email__endswith=f"@{SUPPORTER_EMAIL_DOMAIN}").exists()

    def test_replace_keeps_real_accounts(self, site, roster):
        User = get_user_model()
        member = User.objects.create_user(username="member", email="member@example.com")

        path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
        call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

        assert User.objects.filter(pk=member.pk).exists()

    def test_year_keyed_json_is_accepted(self, site, roster):
        path = roster({"2021": ["Bare Name", {"name": "Grace Hopper", "email": "grace@example.com"}]}, ".json")
        call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

        assert set(FoundationalSupport.objects.values_list("year", flat=True)) == {2021}
        assert get_user_model().objects.filter(display_name="Bare Name").exists()

    def test_a_bad_row_aborts_the_whole_import(self, site, roster):
        before = FoundationalSupport.objects.count()
        path = roster([("Grace Hopper", "grace@example.com", "not-a-year", "listed")])

        with pytest.raises(CommandError):
            call_command("import_foundational_supporters", str(path), "--replace", verbosity=0)

        assert FoundationalSupport.objects.count() == before

    def test_dry_run_writes_nothing(self, site, roster):
        before = FoundationalSupport.objects.count()
        path = roster([("Grace Hopper", "grace@example.com", 2023, "listed")])
        call_command("import_foundational_supporters", str(path), "--replace", "--dry-run", verbosity=0)
        assert FoundationalSupport.objects.count() == before
