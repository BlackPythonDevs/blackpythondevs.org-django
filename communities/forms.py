from django import forms

from .models import Community


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
