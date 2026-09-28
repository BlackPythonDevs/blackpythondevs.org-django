from django.contrib import admin

from .models import Notification, UserNotification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "recipient_count", "sent_at", "created_at")
    list_filter = ("sent_at",)
    search_fields = ("subject", "body", "sender__email", "sender__display_name")
    readonly_fields = ("recipient_count", "sent_at", "created_at")
    filter_horizontal = ("roles",)
    autocomplete_fields = ("sender",)


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ("message", "recipient", "actor", "created_at", "read_at")
    list_filter = ("read_at",)
    search_fields = ("message", "recipient__email", "actor__email")
    autocomplete_fields = ("recipient", "actor")
