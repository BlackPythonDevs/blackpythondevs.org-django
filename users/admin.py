from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import InviteLink, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("email", "username", "display_name", "is_staff")
    search_fields = ("email", "username", "display_name")
    ordering = ("email",)
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "pronouns", "bio")}),
        (
            "Onboarding",
            {
                "fields": (
                    "member_type",
                    "country",
                    "region",
                    "subcommunities",
                    "communication_preferences",
                    "onboarding_completed_at",
                )
            },
        ),
    )
    readonly_fields = ("region", "onboarding_completed_at")


@admin.register(InviteLink)
class InviteLinkAdmin(admin.ModelAdmin):
    """Staff/superusers create these; see InviteLink for the acceptance flow.

    A non-superuser can only grant groups they themselves belong to — that's
    enforced in `formfield_for_manytomany` below, so this page can't be used to
    hand out access the inviter doesn't already have.
    """

    list_display = ("email", "group_list", "status", "created_by", "created_at", "expires_at")
    list_filter = ("groups",)
    search_fields = ("email", "created_by__email", "created_by__display_name")
    autocomplete_fields = ("created_by",)
    filter_horizontal = ("groups",)
    readonly_fields = ("token", "invite_url", "accepted_by", "used_at", "created_at")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("created_by").prefetch_related("groups")

    @admin.display(description="Groups")
    def group_list(self, obj):
        return ", ".join(obj.groups.values_list("name", flat=True)) or "—"

    @admin.display(description="Status")
    def status(self, obj):
        if obj.is_used:
            return "Used"
        if obj.is_expired:
            return "Expired"
        return "Pending"

    @admin.display(description="Invite link")
    def invite_url(self, obj):
        if not obj.pk:
            return "Save to generate the link."
        return obj.get_absolute_url()

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("email", "groups")
        return ("email", "groups", "invite_url", "token", "accepted_by", "used_at", "created_at", "expires_at")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups" and not request.user.is_superuser:
            kwargs["queryset"] = request.user.groups.all()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        messages.info(request, f"Invite link: {request.build_absolute_uri(obj.get_absolute_url())}")
        return super().response_add(request, obj, post_url_continue)

    # Gate on is_staff rather than Django's per-model permission system: "any
    # staff or superuser" can generate invites, full stop. The actual guard
    # against privilege escalation is formfield_for_manytomany above, not a
    # permission a staff member could simply not be granted.
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        # Used/expired invites are kept for the record but shouldn't be editable.
        if obj is not None and not obj.is_valid:
            return False
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)
