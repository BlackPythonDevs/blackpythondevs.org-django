from django import forms
from django.contrib.auth.models import Group

from users.models import User
from users.regions import GROUPED_REGION_CHOICES

from .models import Notification, has_full_access, is_community_partner, is_sponsor


class NotificationForm(forms.ModelForm):
    """The compose form. Which filters are available depends on the sender.

    Staff, superusers, and Executors see all three filters. Sponsors only see
    regions. Community Partners only see affinities, and only the ones they
    identify with themselves — the whole point of the group.
    """

    image = forms.ImageField(
        required=False,
        help_text="Optional. Added to the end of the message as a Markdown image.",
    )
    regions = forms.MultipleChoiceField(
        choices=GROUPED_REGION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave everything unchecked to reach every region.",
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave everything unchecked to skip filtering by group.",
    )
    affinities = forms.MultipleChoiceField(
        choices=User.SUBCOMMUNITY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave everything unchecked to reach everyone, regardless of subcommunity.",
    )

    class Meta:
        model = Notification
        fields = ["subject", "body", "regions", "roles", "affinities"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, sender=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sender = sender

        if sender is not None and not has_full_access(sender):
            if is_sponsor(sender):
                del self.fields["roles"]
                del self.fields["affinities"]
            elif is_community_partner(sender):
                del self.fields["roles"]
                del self.fields["regions"]
                own = set(sender.subcommunities)
                self.fields["affinities"].choices = [
                    choice for choice in User.SUBCOMMUNITY_CHOICES if choice[0] in own
                ]
                self.fields["affinities"].required = True
                self.fields["affinities"].help_text = (
                    "You can only message the subcommunities you're part of yourself."
                )
