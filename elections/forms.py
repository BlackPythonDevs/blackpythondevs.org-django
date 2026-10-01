import datetime as dt

from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from .models import AOE, EARLIEST_TZ, Candidacy, Election, _region_of, election_window_instants

ONE_DAY = dt.timedelta(days=1)


class BallotForm(forms.Form):
    """A ranked-choice ballot: one optional rank field per candidacy.

    Built dynamically off whichever candidacies are running rather than a
    `ModelForm` on `BallotRanking`, since the set of fields depends on the
    election — a voter isn't ranking a fixed schema, they're ranking
    whoever happens to be on the ballot this cycle.

    Each region elects its own representative, so a rank only has to be
    unique among the candidates *in the same region* — the same number
    (e.g. everyone's "1") is expected to recur once per region, one for
    each region's separate race.
    """

    def __init__(self, *args, candidacies, **kwargs):
        super().__init__(*args, **kwargs)
        self.candidacies = list(candidacies)
        for candidacy in self.candidacies:
            self.fields[f"rank_{candidacy.pk}"] = forms.IntegerField(
                required=False,
                min_value=1,
                widget=forms.NumberInput(
                    attrs={
                        "min": 1,
                        "inputmode": "numeric",
                        "class": "ballot-card-input",
                        "aria-label": f"Rank for {candidacy.user.display_name}",
                    }
                ),
            )

    def clean(self):
        cleaned = super().clean()
        ranks_by_region = {}
        for candidacy in self.candidacies:
            value = cleaned.get(f"rank_{candidacy.pk}")
            if value is None:
                continue
            ranks_by_region.setdefault(_region_of(candidacy), []).append(value)

        if not ranks_by_region:
            raise forms.ValidationError("Rank at least one candidate before submitting your ballot.")
        for region, ranks in ranks_by_region.items():
            if len(ranks) != len(set(ranks)):
                raise forms.ValidationError(f"In {region}, give each candidate you rank a different number.")
        return cleaned

    def rankings(self):
        """`[(candidacy, rank), ...]` for every candidate the voter ranked,
        in the order they'll be recorded — sorted by rank."""
        ranked = [
            (candidacy, self.cleaned_data[f"rank_{candidacy.pk}"])
            for candidacy in self.candidacies
            if self.cleaned_data.get(f"rank_{candidacy.pk}") is not None
        ]
        ranked.sort(key=lambda pair: pair[1])
        return ranked


class CandidacyForm(forms.ModelForm):
    class Meta:
        model = Candidacy
        # election and user are set server-side (see CandidacyEditView), so
        # this form only ever exposes the one thing a candidate writes.
        fields = ["statement"]
        labels = {"statement": "Why are you running to be Executor?"}
        widgets = {"statement": forms.Textarea(attrs={"rows": 8})}


class ElectionAdminForm(forms.ModelForm):
    """The Django admin's "add/change election" form.

    `Election`'s four `*_at` fields are UTC instants derived from plain
    dates (see `elections.models.opens_instant`/`closes_instant`) — the
    admin's default split date/time widget would make a staff member work
    out that conversion by hand, exactly the busywork `create_election`
    exists to avoid. This form exposes the same four dates instead and
    computes the instants itself, so the admin and the management command
    behave the same way.
    """

    # AdminDateWidget gives the usual admin calendar-picker + "Today" shortcut
    # without the "Time" input that comes with a plain DateTimeField/
    # AdminSplitDateTime — there's no time to enter, only a date.
    nomination_opens = forms.DateField(
        widget=AdminDateWidget, help_text="The window opens once this date has begun anywhere on Earth."
    )
    nomination_closes = forms.DateField(
        widget=AdminDateWidget, help_text="AOE. The window stays open until this date has ended everywhere."
    )
    voting_opens = forms.DateField(
        widget=AdminDateWidget, help_text="The window opens once this date has begun anywhere on Earth."
    )
    voting_closes = forms.DateField(
        widget=AdminDateWidget, help_text="AOE. The window stays open until this date has ended everywhere."
    )

    class Meta:
        model = Election
        fields = ["year", "intro"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["nomination_opens"].initial = self.instance.nomination_opens_at.astimezone(EARLIEST_TZ).date()
            self.fields["nomination_closes"].initial = (
                self.instance.nomination_closes_at.astimezone(AOE).date() - ONE_DAY
            )
            self.fields["voting_opens"].initial = self.instance.voting_opens_at.astimezone(EARLIEST_TZ).date()
            self.fields["voting_closes"].initial = self.instance.voting_closes_at.astimezone(AOE).date() - ONE_DAY

    def clean(self):
        cleaned = super().clean()
        names = ["nomination_opens", "nomination_closes", "voting_opens", "voting_closes"]
        if any(cleaned.get(name) is None for name in names):
            # A required field is already blank — its own error is enough.
            return cleaned

        instants, errors = election_window_instants(*(cleaned[name] for name in names))
        for name, message in errors.items():
            self.add_error(name, message)
        self._instants = instants
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        for name, value in self._instants.items():
            setattr(instance, f"{name}_at", value)
        if commit:
            instance.save()
        return instance
