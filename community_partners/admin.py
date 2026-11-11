from django.contrib import admin

from .models import CommunityPartner


@admin.register(CommunityPartner)
class CommunityPartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")
    fieldsets = (
        (None, {"fields": ("name", "description", "website")}),
        ("Display", {"fields": ("logo_static_path", "sort_order", "is_active")}),
        ("Internal", {"fields": ("notes",)}),
    )
    readonly_fields = ("created_at", "updated_at")
