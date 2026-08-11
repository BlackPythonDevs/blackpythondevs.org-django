from django import forms

from .models import StudentAmbassador


class AmbassadorApplicationForm(forms.ModelForm):
    class Meta:
        model = StudentAmbassador
        # user, status, and notes are set server-side / managed internally, so
        # they stay off the public form.
        fields = ["name", "email", "school", "field_of_study", "graduation_year", "country", "motivation"]
        widgets = {
            "graduation_year": forms.NumberInput(attrs={"min": 2000, "max": 2100}),
            "motivation": forms.Textarea(attrs={"rows": 5}),
        }
