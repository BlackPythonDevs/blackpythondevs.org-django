"""Student Ambassadors: the ORM record of a member's application to the
Black Python Devs student ambassador programme.

Like the sponsorships app these are plain records, not Wagtail pages. Each
moves through a lifecycle — applied, then either waitlisted, accepted, or
rejected. "Waitlisted" is simply one of the statuses; there is no separate
queue. When an application is accepted the member is added to the
"Ambassadors" auth group (and removed again if they later move off accepted);
that group *is* the roster of ambassadors. The membership sync lives in
signals.py so it fires on create, update, and delete alike.

Applications come in through the public front-end form (see views.py), which
requires the member to be signed in so every application ties back to a User —
the only way the group roster can stay accurate.
"""

from django.conf import settings
from django.db import models
from django_countries.fields import CountryField

# The auth group whose members are the accepted ambassadors. Kept here so the
# data migration and the signals stay in step with a single source of truth.
GROUP_NAME = "Ambassadors"


class StudentAmbassador(models.Model):
    """A member's application to the student ambassador programme."""

    APPLIED = "applied"
    WAITLISTED = "waitlisted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (APPLIED, "Applied"),
        (WAITLISTED, "Waitlisted"),
        (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"),
    ]

    # One application per member. Nullable so records can also be entered by
    # hand in the admin, but the front-end form always sets it — and only
    # applications with a user can be added to the Ambassadors group.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambassador_application",
    )

    name = models.CharField(max_length=200, help_text="The applicant's full name.")
    email = models.EmailField(help_text="Best contact email for the applicant.")
    school = models.CharField(max_length=200, help_text="School, college, or university.")
    country = CountryField(blank=True, help_text="Where the applicant is based.")
    field_of_study = models.CharField(max_length=200, blank=True)
    graduation_year = models.PositiveIntegerField(
        null=True, blank=True, help_text="Expected year of graduation."
    )
    motivation = models.TextField(
        help_text="Why the applicant wants to be a Black Python Devs student ambassador.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=APPLIED,
        db_index=True,
        help_text="Accepted applicants are added to the Ambassadors group.",
    )
    notes = models.TextField(blank=True, help_text="Internal notes. Not shown to the applicant.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "student ambassador"
        verbose_name_plural = "student ambassadors"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_accepted(self):
        return self.status == self.ACCEPTED
