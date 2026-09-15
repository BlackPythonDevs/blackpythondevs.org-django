from django import forms

from communities.models import Community

from .models import CommunityMessage


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
