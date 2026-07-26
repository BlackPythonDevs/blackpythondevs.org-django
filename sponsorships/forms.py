from django import forms

from .models import SponsorshipRequest


class SponsorshipRequestForm(forms.ModelForm):
    class Meta:
        model = SponsorshipRequest
        fields = ["name", "url", "prospectus_url", "start_date", "country", "amount_requested", "notes"]
        widgets = {
            # Native date picker instead of a bare text input.
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            # Plain text box (no number-spinner up/down arrows); still validated
            # as a decimal by the underlying model field.
            "amount_requested": forms.TextInput(attrs={"inputmode": "decimal"}),
        }
