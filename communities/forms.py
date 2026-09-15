from django import forms

from .models import Community, CommunityMessage


class CommunityAdminForm(forms.ModelForm):
    """The self-service edit form for a community admin's own community.

    Deliberately excludes `notes` — that's where staff write things a
    community admin should never see (see the model's help text) — mirroring
    how `sponsorships.PublicSponsorshipRequestForm` drops `notes` for the same
    reason.
    """

    class Meta:
        model = Community
        fields = ["name", "description", "website", "is_online", "country"]


class CommunityMessageForm(forms.ModelForm):
    """The compose form a community admin uses to message leadership.

    `community` is restricted to the communities the sender actually admins —
    passed in explicitly rather than trusted from POST data, since a
    ModelChoiceField still validates against its queryset either way, but this
    also keeps the rendered dropdown from ever listing communities the sender
    doesn't admin.
    """

    class Meta:
        model = CommunityMessage
        fields = ["community", "subject", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, sender=None, **kwargs):
        super().__init__(*args, **kwargs)
        if sender is not None:
            self.fields["community"].queryset = Community.objects.filter(admins=sender)
