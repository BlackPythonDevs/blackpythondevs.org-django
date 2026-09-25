"""Restrict the django-admin audit trail (see AUDITLOG_INCLUDE_ALL_MODELS in
settings) to superusers.

auditlog.apps.AuditlogConfig.ready() registers its own LogEntryAdmin against
the normal permission system, so any staff user granted the `view_logentry`
permission could otherwise read every tracked model's history — including
other users' data. Re-registering here swaps that for a superuser-only check.
"""

from auditlog.admin import LogEntryAdmin
from auditlog.models import LogEntry
from django.contrib import admin

admin.site.unregister(LogEntry)


@admin.register(LogEntry)
class SuperuserOnlyLogEntryAdmin(LogEntryAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
