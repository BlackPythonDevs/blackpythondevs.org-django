"""Corporate sponsor content: the CustomBlogPage announcement type."""

import datetime

import pytest

from blog.models import BlogIndexPage, CustomBlogPage
from core.models import Sponsor

pytestmark = pytest.mark.django_db


@pytest.fixture
def blog_index(site):
    index = BlogIndexPage(title="News", slug="news")
    site.add_child(instance=index)
    index.save_revision().publish()
    return index


@pytest.fixture
def sponsor():
    return Sponsor.objects.create(name="Acme Corp")


def test_custom_blog_page_lives_under_blog_index(blog_index, sponsor):
    page = CustomBlogPage(
        title="Welcome our new sponsor: Acme Corp",
        slug="welcome-acme-corp",
        date=datetime.date(2026, 1, 15),
        sponsor=sponsor,
    )
    blog_index.add_child(instance=page)
    page.save_revision().publish()

    assert page.get_parent().specific == blog_index
    assert page.sponsor_id == sponsor.pk


def test_custom_blog_page_appears_in_blog_index_listing(client, blog_index, sponsor):
    page = CustomBlogPage(
        title="Welcome our new sponsor: Acme Corp",
        slug="welcome-acme-corp",
        date=datetime.date(2026, 1, 15),
        sponsor=sponsor,
    )
    blog_index.add_child(instance=page)
    page.save_revision().publish()

    from django.test import RequestFactory

    posts = blog_index.get_posts(RequestFactory().get("/news/"))
    assert page.pk in [p.pk for p in posts]


def test_custom_blog_page_renders(client, blog_index, sponsor):
    page = CustomBlogPage(
        title="Welcome our new sponsor: Acme Corp",
        slug="welcome-acme-corp",
        date=datetime.date(2026, 1, 15),
        sponsor=sponsor,
        body=[("paragraph", "<p>Say hello to our newest sponsor.</p>")],
    )
    blog_index.add_child(instance=page)
    page.save_revision().publish()

    response = client.get(page.url)
    assert response.status_code == 200
    assert "Welcome our new sponsor" in response.content.decode()


def test_deleting_sponsor_keeps_the_announcement_post(blog_index, sponsor):
    page = CustomBlogPage(
        title="Welcome our new sponsor: Acme Corp",
        slug="welcome-acme-corp",
        date=datetime.date(2026, 1, 15),
        sponsor=sponsor,
    )
    blog_index.add_child(instance=page)
    page.save_revision().publish()

    sponsor.delete()
    page.refresh_from_db()
    assert page.sponsor_id is None
