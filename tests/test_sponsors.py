"""Corporate sponsor lifecycle: expires_at derivation and the status-transition job."""

import datetime

import pytest
from django.core.management import call_command

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
