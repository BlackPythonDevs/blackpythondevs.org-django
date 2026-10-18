from django import forms
from django.contrib.auth import get_user_model

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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # The signed-in applicant, passed by the apply view. Admin-created
        # applications (no user on the form) skip the cross-member check.
        self.user = user

    def clean_email(self):
        """The application is already tied to the signed-in member (the view
        sets `user` server-side), so the email on it shouldn't point at a
        different member's account (issue #144). Prefilled from the profile,
        but a member may keep a school or personal address here — just not
        someone else's.
        """
        email = self.cleaned_data.get("email")
        if (
            email
            and self.user is not None
            and get_user_model().objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists()
        ):
            raise forms.ValidationError(
                "That email address belongs to another member. "
                "Use your own contact address — the application is linked to your account.",
                code="email_taken",
            )
        return email
