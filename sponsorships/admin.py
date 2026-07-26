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
        ("Support", {"fields": ("status", "paid", "amount_requested")}),
        ("Internal", {"fields": ("notes",)}),
        ("Derived", {"fields": ("year", "region"), "classes": ("collapse",)}),
    )
    # year and region are computed on save(); surface them read-only.
    readonly_fields = ("year", "region", "created_at", "updated_at")
