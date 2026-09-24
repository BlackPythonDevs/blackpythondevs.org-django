from django import forms

from core.models import is_leadership_or_above

from .models import ServiceAwardNomination, ServiceAwardRecipient


class ServiceAwardNominationForm(forms.ModelForm):
    class Meta:
        model = ServiceAwardNomination
        # nominator, award_year, status and notes are set server-side or
        # managed by leadership, so they stay off the form.
        fields = [
            "nominee_name",
            "nominee_email",
            "nominee_user",
            "nominee_url",
            "statement",
            "contributions",
        ]
        labels = {
            "nominee_name": "Who are you nominating?",
            "nominee_email": "Their email",
            "nominee_user": "Their site account (optional)",
            "nominee_url": "A link to their work (optional)",
            "statement": "Why do they deserve the Community Service Award?",
            "contributions": "What have they contributed so far?",
        }
        widgets = {
            "statement": forms.Textarea(attrs={"rows": 6}),
            "contributions": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, nominator=None, award_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.nominator = nominator
        self.award_year = award_year
        # A large member list would make this select unusable, but the
        # account link is optional — leaving it blank is always valid.
        self.fields["nominee_user"].required = False

    def clean(self):
        """Catch the eligibility rules and the duplicate before the database
        constraint does.

        The unique constraint only covers (nominator, nominee_email,
        award_year), and two of those three are filled in by the view, so the
        form has to be told about them to raise a readable error instead of
        an IntegrityError. The leadership and past-recipient exclusions have
        no database constraint behind them at all — they're checked here.
        """
        cleaned = super().clean()
        email = cleaned.get("nominee_email")
        nominee_user = cleaned.get("nominee_user")

        if nominee_user is not None and is_leadership_or_above(nominee_user):
            self.add_error("nominee_user", "Leadership team members aren't eligible for this award.")

        if email:
            already_won = ServiceAwardRecipient.objects.filter(recipient_email__iexact=email)
            if nominee_user is not None:
                already_won = already_won | ServiceAwardRecipient.objects.filter(recipient_user=nominee_user)
            if already_won.exists():
                self.add_error("nominee_email", "This person has already received the Community Service Award.")

        if email and self.nominator is not None and self.award_year is not None:
            duplicates = ServiceAwardNomination.objects.filter(
                nominator=self.nominator,
                nominee_email__iexact=email,
                award_year=self.award_year,
            ).exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "nominee_email",
                    "You've already nominated this person for this cycle.",
                )
        return cleaned
