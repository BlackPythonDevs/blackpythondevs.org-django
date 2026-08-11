from django.contrib import admin

from .models import CouncilNomination


@admin.register(CouncilNomination)
class CouncilNominationAdmin(admin.ModelAdmin):
    list_display = ("nominee_name", "term_year", "nominator", "nominee_consulted", "status", "created_at")
    list_filter = ("status", "term_year", "nominee_consulted")
    search_fields = ("nominee_name", "nominee_email", "statement", "notes")
    list_editable = ("status",)
    ordering = ("-term_year", "-created_at")
    autocomplete_fields = ("nominator", "nominee_user")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("nominator", "term_year", "status")}),
        ("Nominee", {"fields": ("nominee_name", "nominee_email", "nominee_user", "nominee_url")}),
        ("The case", {"fields": ("statement", "contributions", "nominee_consulted")}),
        ("Internal", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
