from django.contrib import admin

from .models import StudentAmbassador


@admin.register(StudentAmbassador)
class StudentAmbassadorAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "country", "status", "created_at")
    list_filter = ("status", "country", "graduation_year")
    search_fields = ("name", "email", "school", "notes")
    list_editable = ("status",)
    ordering = ("-created_at",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("user", "name", "email")}),
        ("Studies", {"fields": ("school", "field_of_study", "graduation_year", "country")}),
        ("Application", {"fields": ("motivation", "status", "notes")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.action(description="Accept selected applications")
    def accept(self, request, queryset):
        # Save one-by-one so the group-sync signal fires for each.
        for application in queryset:
            application.status = StudentAmbassador.ACCEPTED
            application.save()

    @admin.action(description="Move selected applications to the waitlist")
    def waitlist(self, request, queryset):
        for application in queryset:
            application.status = StudentAmbassador.WAITLISTED
            application.save()

    @admin.action(description="Reject selected applications")
    def reject(self, request, queryset):
        for application in queryset:
            application.status = StudentAmbassador.REJECTED
            application.save()

    actions = ["accept", "waitlist", "reject"]
