"""Leadership meeting minutes: when leadership meets, and what was said.

A plain record (not a Wagtail page), like `service_award` and `nominations`:
leadership schedules a meeting in the neapolitan console, members download
the calendar entry as an .ics invite, and the published notes become the
minutes. Everything here is leadership-only — see
`core.models.is_leadership_or_above` for who that is.
"""

from datetime import UTC, timedelta

from django.db import models
from django.utils import timezone


class Meeting(models.Model):
    """One leadership meeting: when it happens, where, and its minutes.

    `notes` doubles as the working pad before the meeting and the published
    minutes afterwards — leadership keep them here rather than in a separate
    document so the calendar invite and the record live in one place.
    """

    title = models.CharField(max_length=200, help_text='e.g. "Leadership sync — January".')
    scheduled_at = models.DateTimeField(help_text="When the meeting starts (your local time is UTC).")
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Physical location, if there is one.",
    )
    url = models.URLField(
        blank=True,
        help_text="Video call link, if the meeting is online.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Meeting minutes, published here for leadership.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "meeting"
        verbose_name_plural = "meetings"
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"{self.title} ({timezone.localtime(self.scheduled_at):%d %b %Y})"

    def is_upcoming(self):
        return self.scheduled_at > timezone.now()

    def as_ics(self):
        """This meeting as a single-event RFC 5545 calendar (text/calendar).

        Hand-rolled rather than pulled in via a dependency: one VEVENT with
        the notes as DESCRIPTION is all an invite needs. DTEND assumes an
        hour — invitees can see the full notes and adjust.
        """

        def escape(text):
            # RFC 5545 §3.3.11: backslashes, semicolons, commas and literal
            # newlines must be escaped in TEXT values.
            return (
                str(text)
                .replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\r\n", "\\n")
                .replace("\n", "\\n")
            )

        start = self.scheduled_at.astimezone(UTC)
        end = start + timedelta(hours=1)
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Black Python Devs//Meeting Minutes//EN",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:meeting-{self.pk}@blackpythondevs.org",
            f"DTSTAMP:{timezone.now().astimezone(UTC):%Y%m%dT%H%M%SZ}",
            f"DTSTART:{start:%Y%m%dT%H%M%SZ}",
            f"DTEND:{end:%Y%m%dT%H%M%SZ}",
            f"SUMMARY:{escape(self.title)}",
        ]
        if self.location:
            lines.append(f"LOCATION:{escape(self.location)}")
        if self.url:
            lines.append(f"URL:{self.url}")
        if self.notes:
            lines.append(f"DESCRIPTION:{escape(self.notes)}")
        lines += ["END:VEVENT", "END:VCALENDAR"]
        return "\r\n".join(lines) + "\r\n"
