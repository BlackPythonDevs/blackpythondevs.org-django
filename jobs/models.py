"""Job postings from corporate sponsors.

A `Job` belongs to exactly one `corporate_sponsorships.Sponsor`. Storage, the
public read-only pages, and the sponsor-champion console live here; the
key-authenticated feed API is a later part of #222.

Ingested fields (title, description, apply_url, ...) will eventually arrive
from third-party job feeds, so they are treated as untrusted:

* URLs go through Django's ``URLField`` (``URLValidator``), which rejects
  ``javascript:``/``data:`` and scheme-less protocol-relative values.
* Titles/descriptions are stored as plain text — nothing here calls
  ``mark_safe``; the template layer's autoescaping is the only render path.
* The public vs. internal field surface is fixed *now* by explicit field
  tuples (``PUBLIC_FIELDS`` / ``INTERNAL_FIELDS``) rather than ``__all__``, so
  later ingestion/view code has a single allowlist to share and cannot
  accidentally expose internal bookkeeping.
"""

from django.core.validators import URLValidator
from django.db import models

from core.models import CORPORATE_SPONSOR_GROUP_NAME

# Only http(s). Django's URLValidator also allows ftp/ftps by default, which
# is never a legitimate scheme for a job application link.
_APPLY_URL_VALIDATOR = URLValidator(schemes=["http", "https"])

# The full permission set a sponsor champion must hold to reach the jobs
# console. Mirrors jobs.views.JobChampionView.permission_required.
JOB_CHAMPION_PERMS = (
    "jobs.view_job",
    "jobs.add_job",
    "jobs.change_job",
    "jobs.delete_job",
)


def can_champion_jobs(user):
    """Whether `user` may manage their sponsor's jobs (issue #224).

    Needs all three: the "Corporate Sponsor" group, a corporation_affiliate,
    and every Job permission the console demands. Deliberately stricter than
    group membership alone so a stray grant or a bare group membership is not
    enough. Superusers get no pass here — the console writes only *their own*
    sponsor's jobs, and a superuser with no affiliation owns none; site admins
    manage every sponsor from the Django admin instead.
    """
    if not user.is_authenticated:
        return False
    if user.corporation_affiliate_id is None:
        return False
    group = getattr(user, "groups", None)
    if group is None or not group.filter(name=CORPORATE_SPONSOR_GROUP_NAME).exists():
        return False
    return user.has_perms(JOB_CHAMPION_PERMS)


class JobQuerySet(models.QuerySet):
    """Queryset helpers for the public jobs pages."""

    def public(self):
        """Jobs that may render on the public site.

        Both flags must agree: `is_published` is the explicit publish toggle
        and `status` must be `published` (so drafts and expired postings never
        leak, even if the toggle was left on).
        """
        return self.filter(is_published=True, status=Job.STATUS_PUBLISHED)


class Job(models.Model):
    """One job posting associated with a corporate sponsor."""

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_EXPIRED, "Expired"),
    ]

    EMPLOYMENT_FULL_TIME = "full_time"
    EMPLOYMENT_PART_TIME = "part_time"
    EMPLOYMENT_CONTRACT = "contract"
    EMPLOYMENT_INTERNSHIP = "internship"
    EMPLOYMENT_OTHER = "other"
    EMPLOYMENT_TYPE_CHOICES = [
        (EMPLOYMENT_FULL_TIME, "Full-time"),
        (EMPLOYMENT_PART_TIME, "Part-time"),
        (EMPLOYMENT_CONTRACT, "Contract"),
        (EMPLOYMENT_INTERNSHIP, "Internship"),
        (EMPLOYMENT_OTHER, "Other"),
    ]

    # --- Public surface: safe to render on a public page. ---
    PUBLIC_FIELDS = (
        "id",
        "title",
        "description",
        "apply_url",
        "location",
        "remote",
        "employment_type",
        "sponsor",
        "published_at",
    )
    # --- Internal surface: never expose on a public page. ---
    INTERNAL_FIELDS = (
        "id",
        "status",
        "is_published",
        "source",
        "external_id",
        "created_at",
        "updated_at",
    )

    sponsor = models.ForeignKey(
        "corporate_sponsorships.Sponsor",
        on_delete=models.CASCADE,
        related_name="jobs",
        help_text="The corporate sponsor this posting belongs to.",
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    apply_url = models.URLField(validators=[_APPLY_URL_VALIDATOR])
    location = models.CharField(max_length=200, blank=True)
    remote = models.BooleanField(default=False)
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default=EMPLOYMENT_FULL_TIME,
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    # Provenance for later feed ingestion. Unique together so a re-run updates
    # the same row instead of duplicating it.
    source = models.CharField(max_length=100, blank=True)
    external_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # `objects` gains the `.public()` helper used by the public pages.
    objects = JobQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=models.Q(source__gt="") & models.Q(external_id__gt=""),
                name="jobs_job_unique_source_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=["is_published", "status"]),
        ]

    def __str__(self):
        return self.title

    def get_public_data(self):
        """Return only the fields safe for a public page.

        Explicit allowlist so later views can't accidentally serialize an
        internal field along with the public ones.
        """
        return {field: getattr(self, field) for field in self.PUBLIC_FIELDS}
