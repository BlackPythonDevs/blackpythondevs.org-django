"""Job postings from corporate sponsors.

A `Job` belongs to exactly one `corporate_sponsorships.Sponsor`. Storage, the
public read-only pages, the sponsor-champion console, and the key-authenticated
write API live here; the outbound feed import is a later part of #222.

Ingested fields (title, description, apply_url, ...) arrive from third-party
job feeds, so they are treated as untrusted:

* URLs go through Django's ``URLField`` (``URLValidator``), which rejects
  ``javascript:``/``data:`` and scheme-less protocol-relative values.
* Titles/descriptions are stored as plain text — nothing here calls
  ``mark_safe``; the template layer's autoescaping is the only render path.
* The public vs. internal field surface is fixed by explicit field tuples
  (``PUBLIC_FIELDS`` / ``INTERNAL_FIELDS``) rather than ``__all__``, so
  ingestion/view code has a single allowlist to share and cannot accidentally
  expose internal bookkeeping.
"""

import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

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


# Separator between the public key id and the secret in a presented key. The
# id is not a secret (it indexes the row); the secret is what `check_password`
# verifies. `key_id` is generated with `secrets.token_urlsafe(12)` and is
# unique, so lookup is a single indexed row rather than a scan-and-compare.
KEY_ID_BYTES = 12
KEY_SECRET_BYTES = 32
API_KEY_SEPARATOR = "."


def generate_api_key():
    """Return ``(key_id, presented_key)`` for a freshly minted key.

    ``presented_key`` is the only time the secret exists in plaintext; callers
    must hand it to the caller and then forget it. Nothing here stores it.
    """
    key_id = secrets.token_urlsafe(KEY_ID_BYTES)
    secret = secrets.token_urlsafe(KEY_SECRET_BYTES)
    return key_id, f"{key_id}{API_KEY_SEPARATOR}{secret}"


def parse_api_key(presented):
    """Split a presented key into ``(key_id, secret)`` or return ``None``.

    Tolerant of a missing separator: lookup by the whole string then fails to
    match any row and the caller returns the same 401 as an unknown key, so
    the shape of a bad key never leaks through the response.
    """
    if not isinstance(presented, str) or API_KEY_SEPARATOR not in presented:
        return None
    key_id, _, secret = presented.partition(API_KEY_SEPARATOR)
    if not key_id or not secret:
        return None
    return key_id, secret


class JobAPIKey(models.Model):
    """A project-issued key letting a sponsor push jobs in from a feed.

    Only a one-way hash of the secret is stored (``key_hash``); the plaintext
    exists once, in ``JobAPIKey.issue()``'s return value, and is never written
    to the database, logs, templates, URLs, audit entries, or error responses.

    These are *our* keys, not the sponsor's Ashby/Greenhouse/Rippling
    credentials — no third-party credential is ever accepted or stored.
    """

    key_id = models.CharField(max_length=64, unique=True, editable=False)
    key_hash = models.CharField(max_length=128, editable=False)
    label = models.CharField(max_length=120, blank=True)

    sponsor = models.ForeignKey(
        "corporate_sponsorships.Sponsor",
        on_delete=models.CASCADE,
        related_name="api_keys",
        help_text="Every job this key writes is scoped to this sponsor.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs_api_keys",
    )

    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "job API key"
        verbose_name_plural = "job API keys"

    def __str__(self):
        # Never include the hash or the secret in string representations that
        # end up in logs, admin templates, or audit entries.
        return f"JobAPIKey {self.key_id} ({self.label or 'unlabelled'})"

    @classmethod
    def issue(cls, sponsor, *, label="", created_by=None, expires_at=None):
        """Create a key and return ``(instance, presented_key)``.

        The plaintext ``presented_key`` is the caller's to store (e.g. show
        once in the admin) and is not retained anywhere on the model.
        """
        key_id, presented = generate_api_key()
        _, secret = presented.split(API_KEY_SEPARATOR, 1)
        obj = cls.objects.create(
            key_id=key_id,
            key_hash=make_password(secret),
            label=label,
            sponsor=sponsor,
            created_by=created_by,
            expires_at=expires_at,
        )
        return obj, presented

    def is_active(self):
        """Whether the key would authenticate right now."""
        if not self.active or self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True

    def verify(self, secret):
        """Constant-time check of a presented secret against the stored hash."""
        if not secret:
            return False
        return check_password(secret, self.key_hash)

    def revoke(self):
        """Permanently disable the key. Kept for audit/reference, not deleted."""
        self.active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["active", "revoked_at"])

    def touch(self):
        """Record successful use without bumping ``updated_at``-style fields."""
        self.last_used = timezone.now()
        self.save(update_fields=["last_used"])
