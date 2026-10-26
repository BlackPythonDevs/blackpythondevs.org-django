"""Confidential Code of Conduct reports, filed on the website and worked by
the CoC team.

A report is a plain record, not a Wagtail page. Every one carries:

- the incident description, in the reporter's own words;
- a status (`under_review` on creation, `closed` when the CoC team is done —
  no other transition exists, enforced in `forms.CocReportStatusForm`);
- `date_reported`, set once at creation and never edited;
- the submitting user (`reporter`), captured even when the reporter files
  anonymously, so the CoC team can notify them of the outcome.

Anonymity and identity, deliberately:

- `reporter` is captured for notification only. It is excluded from every
  viewer-facing surface — the report detail page and the Django admin
  fieldsets alike — and nothing renders it back to anyone.
- The model is excluded from django-auditlog (see
  `AUDITLOG_EXCLUDE_TRACKING_MODELS` in bpd/settings/base.py): the audit log
  records the request's user as the actor of every write, which would name
  the reporter on their own report, and its stored copies of the report text
  would be readable by every superuser. See `elections.models.Ballot` for
  the same reasoning.
- `__str__` reveals nothing but the id and status — it is what renders as
  the object heading in the checklists console and its object lists.

A report cannot be un-created: no view, URL, admin action, or permission
anywhere — including for superusers in the Django admin's delete flow —
deletes a row (see coc_reports/admin.py and the COC Report Viewing group's
permissions in migration 0002).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class CocReport(models.Model):
    """One Code of Conduct report, filed through the website's intake form."""

    UNDER_REVIEW = "under_review"
    CLOSED = "closed"
    STATUS_CHOICES = [
        (UNDER_REVIEW, "Under review"),
        (CLOSED, "Closed"),
    ]

    description = models.TextField(help_text="The incident, in the reporter's own words.")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=UNDER_REVIEW,
        db_index=True,
        help_text="Under review from creation; closed when the CoC team has concluded. No other transition exists.",
    )
    date_reported = models.DateField(
        default=timezone.now,
        editable=False,
        help_text="The day the report was filed. Set once at creation; never edited.",
    )

    # Captured so the reporter can be notified of the outcome, even when they
    # file anonymously. Never rendered to report viewers — see this module's
    # docstring. Null for a logged-out reporter; SET_NULL so deleting an
    # account never deletes (or blocks deleting) the report itself.
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="coc_reports_filed",
        editable=False,
    )
    is_anonymous = models.BooleanField(
        default=False,
        help_text="Whether the reporter asked to stay anonymous to the person reported on.",
    )

    class Meta:
        verbose_name = "CoC report"
        verbose_name_plural = "CoC reports"
        ordering = ["-date_reported", "-pk"]
        # Nothing here grants delete; nothing anywhere does. The COC Report
        # Viewing group gets view + change only (migration 0002).

    def __str__(self):
        # Rendered in the checklists console's object lists and detail page
        # heading: deliberately says nothing about the report's contents.
        return f"CoC report #{self.pk} ({self.get_status_display()})"
