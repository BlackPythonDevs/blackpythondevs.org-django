"""Corporate sponsor lifecycle: expires_at derivation, the status-transition
job, and the CustomBlogPage announcement type."""

import datetime

import pytest
from django.core.management import call_command

from blog.models import BlogIndexPage, CustomBlogPage
from core.models import Sponsor

pytestmark = pytest.mark.django_db


def make_sponsor(**kwargs):
    defaults = {"name": "Acme Corp", "status": Sponsor.STATUS_ACTIVE, "active": True}
    defaults.update(kwargs)
    return Sponsor.objects.create(**defaults)


def test_expires_at_derived_from_invoice_paid_date():
    sponsor = make_sponsor(invoice_paid_date=datetime.date(2026, 1, 15))
    assert sponsor.expires_at == datetime.date(2027, 1, 15)


def test_expires_at_stays_none_without_invoice_paid_date():
    sponsor = make_sponsor()
    assert sponsor.expires_at is None


def test_update_status_leaves_sponsor_without_invoice_date_alone():
    sponsor = make_sponsor()
    call_command("update_sponsor_status")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_ACTIVE
    assert sponsor.active is True


def test_update_status_marks_expiring_soon_within_window(today=datetime.date.today()):
    sponsor = make_sponsor(invoice_paid_date=today - datetime.timedelta(days=340))
    call_command("update_sponsor_status")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_EXPIRING_SOON
    assert sponsor.active is True


def test_update_status_leaves_far_out_sponsor_active(today=datetime.date.today()):
    sponsor = make_sponsor(invoice_paid_date=today - datetime.timedelta(days=10))
    call_command("update_sponsor_status")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_ACTIVE


def test_update_status_expires_and_hides_from_strip(today=datetime.date.today()):
    sponsor = make_sponsor(invoice_paid_date=today - datetime.timedelta(days=366))
    call_command("update_sponsor_status")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_EXPIRED
    assert sponsor.active is False


def test_update_status_expires_exactly_on_expiry_date(today=datetime.date.today()):
    sponsor = make_sponsor(invoice_paid_date=today - datetime.timedelta(days=365))
    call_command("update_sponsor_status")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_EXPIRED


def test_dry_run_changes_nothing(today=datetime.date.today()):
    sponsor = make_sponsor(invoice_paid_date=today - datetime.timedelta(days=366))
    call_command("update_sponsor_status", "--dry-run")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_ACTIVE
    assert sponsor.active is True


def test_update_status_does_not_touch_cancelled_sponsor(today=datetime.date.today()):
    sponsor = make_sponsor(
        invoice_paid_date=today - datetime.timedelta(days=366),
        status=Sponsor.STATUS_CANCELLED,
        active=False,
    )
    call_command("update_sponsor_status")
    sponsor.refresh_from_db()
    assert sponsor.status == Sponsor.STATUS_CANCELLED


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
