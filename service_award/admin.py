from django.contrib import admin

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


@admin.register(ServiceAwardRecipient)
class ServiceAwardRecipientAdmin(admin.ModelAdmin):
    list_display = ("recipient_name", "award_year", "recipient_user", "created_at")
    list_filter = ("award_year",)
    search_fields = ("recipient_name", "recipient_email", "notes")
    ordering = ("-award_year",)
    autocomplete_fields = ("recipient_user", "nomination")
    readonly_fields = ("created_at",)
