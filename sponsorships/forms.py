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


class PublicSponsorshipRequestForm(SponsorshipRequestForm):
    """The form event organisers fill in themselves.

    Same fields as the staff console minus `notes`, which is where reviewers
    write things the requester should never see. Status stays at its default
    (requested) — nobody submits an already-approved request.
    """

    class Meta(SponsorshipRequestForm.Meta):
        fields = [f for f in SponsorshipRequestForm.Meta.fields if f != "notes"]
        labels = {
            "name": "Event name",
            "url": "Event website",
            "prospectus_url": "Sponsorship prospectus",
            "amount_requested": "Amount you're asking for",
        }
        help_texts = {
            "amount_requested": "Optional. Include the currency if it isn't USD.",
        }
