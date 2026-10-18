from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import ServiceAwardNomination, ServiceAwardRecipient


@admin.register(ServiceAwardNomination)
class ServiceAwardNominationAdmin(admin.ModelAdmin):
    list_display = ("nominee_name", "award_year", "nominator", "status", "created_at")
    list_filter = ("status", "award_year")
    search_fields = ("nominee_name", "nominee_email", "statement", "notes")
    list_editable = ("status",)
    ordering = ("-award_year", "-created_at")
    autocomplete_fields = ("nominator", "nominee_user")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("nominator", "award_year", "status")}),
        ("Nominee", {"fields": ("nominee_name", "nominee_email", "nominee_user", "nominee_url")}),
        ("The case", {"fields": ("statement", "contributions")}),
        ("Internal", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


class ServiceAwardRecipientForm(forms.ModelForm):
    """Links the recipient to their site account by email (issue #144).

    Recipients are recorded by leadership in the admin, so the admin form is
    the one place the link is made. Matching `recipient_email` against member
    accounts — the same way nomination forms do — means a recipient who is
    already a member is linked without anyone hunting for them in a member
    list, and the exclusion check in ServiceAwardNominationForm.clean() then
    also matches them by account, not just by the bare email string.
    """

    class Meta:
        model = ServiceAwardRecipient
        fields = ["recipient_name", "recipient_email", "recipient_user", "nomination", "award_year", "notes"]

    def save(self, commit=True):
        recipient = super().save(commit=False)
        email = recipient.recipient_email
        if email:
            recipient.recipient_user = get_user_model().objects.filter(email__iexact=email).first()
        else:
            recipient.recipient_user = None
        if commit:
            recipient.save()
        return recipient


@admin.register(ServiceAwardRecipient)
class ServiceAwardRecipientAdmin(admin.ModelAdmin):
    form = ServiceAwardRecipientForm
    list_display = ("recipient_name", "award_year", "recipient_user", "created_at")
    list_filter = ("award_year",)
    search_fields = ("recipient_name", "recipient_email", "notes")
    ordering = ("-award_year",)
    autocomplete_fields = ("recipient_user", "nomination")
    readonly_fields = ("created_at",)
