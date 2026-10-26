"""Django admin for CoC reports: read-and-work, never create or delete.

A report cannot be un-created, so this admin has no add and no delete —
not even for superusers — and the delete action is removed outright.
`reporter` is deliberately absent from the fieldsets: it exists only for
notification (see coc_reports.models), and no admin surface should render
it back. Reports are made on the website's public form, which is also what
captures the submitting user and seeds the checklist.
"""

from django.contrib import admin

from .models import CocReport


@admin.register(CocReport)
class CocReportAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "date_reported", "is_anonymous")
    list_filter = ("status", "date_reported")
    readonly_fields = ("date_reported",)
    fieldsets = (
        (None, {"fields": ("description", "status")}),
        ("Filed", {"fields": ("date_reported", "is_anonymous")}),
    )

    # Reports are made on the website, which is what captures the reporter
    # and seeds the checklist.
    def has_add_permission(self, request):
        return False

    # A report cannot be un-created — no delete permission, no delete action.
    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
