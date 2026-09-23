from django import forms

from .models import Candidacy


class CandidacyForm(forms.ModelForm):
    class Meta:
        model = Candidacy
        # election and user are set server-side (see CandidacyEditView), so
        # this form only ever exposes the one thing a candidate writes.
        fields = ["statement"]
        labels = {"statement": "Why are you running for the council?"}
        widgets = {"statement": forms.Textarea(attrs={"rows": 8})}
