"""Forms for filing and working CoC reports.

`CocReportForm` is the public intake form: the description plus the
anonymity choice. `reporter` and `date_reported` are never on it — the view
captures the submitting user, and the date is set once at creation.

`CocReportStatusForm` is the CoC team's only write surface: it can move a
report from under review to closed, and nothing else. It refuses to re-open
a closed report or invent any other transition (the security condition on
this issue), server-side, not just in the UI.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import CocReport


class CocReportForm(forms.ModelForm):
    class Meta:
        model = CocReport
        fields = ["description", "is_anonymous"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8, "cols": None}),
        }
        labels = {
            "is_anonymous": "File this report anonymously",
        }
        help_texts = {
            "is_anonymous": (
                "We still record who filed the report — only so we can tell you the "
                "outcome — but your name stays out of the report and away from the "
                "person it is about."
            ),
        }


class CocReportStatusForm(forms.ModelForm):
    class Meta:
        model = CocReport
        fields = ["status"]

    def clean(self):
        cleaned = super().clean()
        new_status = cleaned.get("status")
        if new_status and self.instance and self.instance.pk:
            if self.instance.status == CocReport.CLOSED:
                raise ValidationError("A closed report stays closed; it cannot be re-opened or changed.")
            if new_status != CocReport.CLOSED:
                raise ValidationError("The only status change available is from “Under review” to “Closed”.")
        return cleaned
