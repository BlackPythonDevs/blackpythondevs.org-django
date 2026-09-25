from django import forms

from .models import CouncilNomination


class CouncilNominationForm(forms.ModelForm):
    class Meta:
        model = CouncilNomination
        # nominator, nominee_user, term_year, status and notes are set
        # server-side or managed by the council, so they stay off the form.
        # nominee_user in particular is never picked from a member list — the
        # council links an account later, from the admin, if it turns out the
        # nominee already has one.
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

    def clean(self):
        """Catch the duplicate before the database constraint does.

        The unique constraint is on (nominator, nominee_email, term_year), and
        two of those three are filled in by the view, so the form has to be told
        about them to raise a readable error instead of an IntegrityError.
        """
        cleaned = super().clean()
        email = cleaned.get("nominee_email")
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
