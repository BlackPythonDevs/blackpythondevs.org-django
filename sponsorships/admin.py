from django.contrib import admin

from .models import SponsorshipRequest


@admin.register(SponsorshipRequest)
class SponsorshipRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "country", "region", "status", "paid", "amount_requested")
    list_filter = ("status", "paid", "country", "year")
    search_fields = ("name", "notes")
    ordering = ("-year", "region", "name")
    list_editable = ("status", "paid")
    fieldsets = (
        (None, {"fields": ("name", "url", "prospectus_url")}),
        ("Event", {"fields": ("start_date", "country")}),
        ("Contact", {"fields": ("contact_name", "contact_email", "contact_user")}),
        ("Support", {"fields": ("status", "paid", "amount_requested")}),
        ("Internal", {"fields": ("notes",)}),
        ("Derived", {"fields": ("year", "region"), "classes": ("collapse",)}),
    )
    # year and region are computed on save(); surface them read-only.
    # contact_user is derived from contact_email on save() the same way.
    readonly_fields = ("year", "region", "contact_user", "created_at", "updated_at")
