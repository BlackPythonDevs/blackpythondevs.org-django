from django import forms

from .models import Job


class JobForm(forms.ModelForm):
    """Create/edit form for a sponsor champion.

    `sponsor` is deliberately absent: the owning sponsor is set in the view
    from `request.user.corporation_affiliate`, so a `sponsor` id in POST can
    never widen a champion's scope to another company.
    """

    class Meta:
        model = Job
        fields = [
            "title",
            "description",
            "apply_url",
            "location",
            "remote",
            "employment_type",
            "status",
            "is_published",
        ]
        help_texts = {
            "status": "A posting appears on the public jobs page only when the status is Published "
            'and "published" is ticked.',
        }
