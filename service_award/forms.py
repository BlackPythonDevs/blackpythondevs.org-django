from django import forms
from django.contrib.auth import get_user_model

from core.models import EXECUTOR_GROUP_NAME

from .models import ServiceAwardNomination, ServiceAwardRecipient


class ServiceAwardNominationForm(forms.ModelForm):
    class Meta:
        model = ServiceAwardNomination
        # nominator, nominee_user, award_year, status and notes are set
        # server-side or managed by leadership, so they stay off the form.
        # nominee_user in particular is never picked from a member list —
        # see clean() — it's only ever matched by email.
        fields = [
            "nominee_name",
            "nominee_email",
            "nominee_url",
            "statement",
            "contributions",
        ]
        labels = {
            "nominee_name": "Who are you nominating?",
            "nominee_email": "Their email",
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
        # Set in clean() once we know which case we're in: a brand new
        # nomination (neither), a genuine duplicate (blocked outright), or a
        # withdrawn one the nominator is bringing back (set once they've
        # confirmed via the "reinstate" button — see the template).
        self.matched_nominee_user = None
        self.reinstate_target = None
        self.needs_reinstate_confirmation = False

    def clean(self):
        """Match the nominee to a site account by email, and catch the
        eligibility rules and the duplicate before the database constraint
        does.

        There's deliberately no field for picking a site account — a large
        member list would make a select unusable, and it invites picking the
        wrong "Jay Miller". Matching by email is the only way in, and it
        happens here rather than as a form field so a nominator can't
        override it.

        The unique constraint only covers (nominator, nominee_email,
        award_year), and two of those three are filled in by the view, so the
        form has to be told about them to raise a readable error instead of
        an IntegrityError. The Executor and past-recipient exclusions have no
        database constraint behind them at all — they're checked here too.

        A withdrawn nomination for the same person doesn't count as that
        duplicate — resubmitting is presumably deliberate — but it isn't
        silently reinstated either, since the nominator may have just
        forgotten they'd already withdrawn. `needs_reinstate_confirmation`
        tells the view/template to ask first; the "reinstate" button in the
        template resubmits with that confirmation.
        """
        cleaned = super().clean()
        email = cleaned.get("nominee_email")
        nominee_user = get_user_model().objects.filter(email__iexact=email).first() if email else None
        self.matched_nominee_user = nominee_user

        if nominee_user is not None and nominee_user.groups.filter(name=EXECUTOR_GROUP_NAME).exists():
            self.add_error("nominee_email", "Executors aren't eligible for this award.")

        if email:
            already_won = ServiceAwardRecipient.objects.filter(recipient_email__iexact=email)
            if nominee_user is not None:
                already_won = already_won | ServiceAwardRecipient.objects.filter(recipient_user=nominee_user)
            if already_won.exists():
                self.add_error("nominee_email", "This person has already received the Community Service Award.")

        if email and self.nominator is not None and self.award_year is not None:
            existing = ServiceAwardNomination.objects.filter(
                nominator=self.nominator,
                nominee_email__iexact=email,
                award_year=self.award_year,
            ).exclude(pk=self.instance.pk)
            if existing.exclude(status=ServiceAwardNomination.WITHDRAWN).exists():
                self.add_error(
                    "nominee_email",
                    "You've already nominated this person for this cycle.",
                )
            else:
                withdrawn = existing.filter(status=ServiceAwardNomination.WITHDRAWN).first()
                if withdrawn is not None:
                    if self.data.get("reinstate") == "true":
                        self.reinstate_target = withdrawn
                    else:
                        self.needs_reinstate_confirmation = True
                        self.add_error(
                            "nominee_email",
                            "You withdrew a nomination for this person earlier this cycle. "
                            "Confirm below to reinstate it instead of starting a new one.",
                        )
        return cleaned

    def save(self, commit=True):
        if self.reinstate_target is not None:
            nomination = self.reinstate_target
            for field in ("nominee_name", "nominee_email", "nominee_url", "statement", "contributions"):
                setattr(nomination, field, self.cleaned_data[field])
            nomination.nominee_user = self.matched_nominee_user
            nomination.status = ServiceAwardNomination.SUBMITTED
            if commit:
                nomination.save()
            self.instance = nomination
            return nomination

        instance = super().save(commit=False)
        instance.nominee_user = self.matched_nominee_user
        if commit:
            instance.save()
        return instance
