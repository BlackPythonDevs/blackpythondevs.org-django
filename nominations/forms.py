from django import forms
from django.contrib.auth import get_user_model

from .models import CouncilNomination, NominationObjection


class CouncilNominationForm(forms.ModelForm):
    class Meta:
        model = CouncilNomination
        # nominator, nominee_user, term_year, status and notes are set
        # server-side or managed by the council, so they stay off the form.
        # nominee_user is never picked from a member list — it's matched
        # automatically from nominee_email in clean() (see issue #144), so a
        # nominee who already has an account is linked the moment they're
        # nominated. The council can still correct the link in the admin.
        fields = [
            "nominee_name",
            "nominee_email",
            "nominee_url",
            "statement",
            "contributions",
            "nominee_consulted",
        ]
        labels = {
            "nominee_name": "Who are you nominating?",
            "nominee_email": "Their email",
            "nominee_url": "A link to their work (optional)",
            "statement": "Why should they serve on the council?",
            "contributions": "What have they contributed so far?",
            "nominee_consulted": "I've confirmed they're willing to serve",
        }
        widgets = {
            "statement": forms.Textarea(attrs={"rows": 6}),
            "contributions": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, nominator=None, term_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.nominator = nominator
        self.term_year = term_year
        # Set in clean(): the site account matching nominee_email, if the
        # nominee is already a member (matched case-insensitively, the same
        # way allauth looks accounts up by email). None means no account yet —
        # the confirmation invite is still how they get one.
        self.matched_nominee_user = None

    def clean(self):
        """Match the nominee to a site account by email, and catch the
        duplicate before the database constraint does.

        Matching happens here rather than as a form field so a nominator
        can't override it, and so the record links to the nominee's account
        as soon as one exists (issue #144) — that keeps the nominee's email
        tied to a member record that can be redacted if they later delete
        their account, rather than living on as a bare string forever.

        The unique constraint is on (nominator, nominee_email, term_year), and
        two of those three are filled in by the view, so the form has to be told
        about them to raise a readable error instead of an IntegrityError.
        """
        cleaned = super().clean()
        email = cleaned.get("nominee_email")
        if email:
            self.matched_nominee_user = get_user_model().objects.filter(email__iexact=email).first()
        if email and self.nominator is not None and self.term_year is not None:
            duplicates = CouncilNomination.objects.filter(
                nominator=self.nominator,
                nominee_email__iexact=email,
                term_year=self.term_year,
            ).exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "nominee_email",
                    "You've already nominated this person for this cycle.",
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.nominee_user = self.matched_nominee_user
        if commit:
            instance.save()
        return instance


class NominationObjectionForm(forms.ModelForm):
    class Meta:
        model = NominationObjection
        fields = ["reason"]
        labels = {"reason": "Why are you objecting to this nomination?"}
        widgets = {"reason": forms.Textarea(attrs={"rows": 4})}
