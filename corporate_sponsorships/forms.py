from django import forms

from .models import Sponsor


class SponsorForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        fields = [
            "name",
            "url",
            "logo",
            "logo_static_path",
            "sort_order",
            "active",
            "status",
            "invoice_paid_date",
            "contract_amount",
            "primary_contact_name",
            "primary_contact_email",
        ]
        widgets = {
            # Native date picker instead of a bare text input.
            "invoice_paid_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            # Plain text box (no number-spinner up/down arrows); still validated
            # as a decimal by the underlying model field.
            "contract_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
        }
        help_texts = {
            "logo": "Upload new logos in the Images admin (/cms/images/) first, then pick one here.",
        }
