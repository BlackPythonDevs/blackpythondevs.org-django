import datetime

import pytest

from blog.models import BlogIndexPage, BlogPage
from core.models import Author, Leader, Sponsor
from events.models import EventIndexPage
from home.models import AboutPage, StandardPage, SupportPage

pytestmark = pytest.mark.django_db


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
