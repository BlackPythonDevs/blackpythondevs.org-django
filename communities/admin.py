from django.contrib import admin

from .models import Community, CommunityAdmin


class CommunityAdminInline(admin.TabularInline):
    model = CommunityAdmin
    extra = 1
    autocomplete_fields = ("user",)


@admin.register(Community)
class CommunityModelAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "is_online", "country")
    list_filter = ("is_online", "region")
    search_fields = ("name", "notes")
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "description", "website")}),
        ("Location", {"fields": ("is_online", "country")}),
        ("Internal", {"fields": ("notes",)}),
        ("Derived", {"fields": ("region",), "classes": ("collapse",)}),
    )
    readonly_fields = ("region", "created_at", "updated_at")
    inlines = [CommunityAdminInline]
