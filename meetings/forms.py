"""Form for the meeting-minutes console.

Follows core.forms.SponsorForm: a ModelForm that swaps the bare text input
for a native browser picker — here a `datetime-local` input for
`scheduled_at`, so leadership get a real date/time picker instead of typing
a timestamp by hand.
"""

from django import forms

from .models import Meeting


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            "title",
            "scheduled_at",
            "location",
            "url",
            "notes",
        ]
        widgets = {
            # Native date/time picker instead of a bare text input.
            # The widget format matches what <input type="datetime-local">
            # submits ("2026-02-01T18:30") and what Django's default
            # DATETIME_INPUT_FORMATS already accept back in.
            "scheduled_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }
