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
        fields = ["description", "reported_name", "response_email", "is_anonymous"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8, "cols": None}),
        }
        labels = {
            "reported_name": "Reported person's name",
            "response_email": "Response email",
            "is_anonymous": "File this report anonymously",
        }
        help_texts = {
            "reported_name": "The name of the person this report is about, if you know it.",
            "response_email": "Where the Code of Conduct team can reach you about this report.",
            "is_anonymous": (
                "We still record who filed the report — only so we can tell you the "
                "outcome — but your name stays out of the report and away from the "
                "person it is about."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional at the model level (additive migration); required on intake.
        self.fields["response_email"].required = True


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
