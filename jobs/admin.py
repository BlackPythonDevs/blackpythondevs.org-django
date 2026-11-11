"""Staff-gated Django admin for Job and JobAPIKey records.

The neapolitan/web consoles later (#222) are separate; this is the plain
admin an administrator uses to seed jobs by hand and to issue/revoke the
project API keys external posting feeds authenticate with.
"""

from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.utils.html import format_html

from .models import Job, JobAPIKey


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "sponsor",
        "location",
        "remote",
        "employment_type",
        "status",
        "is_published",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_published", "status", "remote", "employment_type", "source")
    search_fields = ("title", "location", "sponsor__name")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(JobAPIKey)
class JobAPIKeyAdmin(admin.ModelAdmin):
    """Issue and revoke the keys the write API accepts.

    The secret is shown exactly once, when the key is created, via the
    `one_time_secret` column; the stored `key_hash` is never listed, searched,
    or rendered anywhere (and the model is excluded from the audit log).
    """

    list_display = ("label", "key_id", "sponsor", "active", "expires_at", "last_used", "created_at")
    list_filter = ("active", "sponsor")
    search_fields = ("label", "key_id", "sponsor__name")
    readonly_fields = ("key_id", "last_used", "created_at", "revoked_at", "one_time_secret")
    fields = (
        "label",
        "sponsor",
        "created_by",
        "active",
        "expires_at",
        "key_id",
        "one_time_secret",
        "last_used",
        "created_at",
        "revoked_at",
    )
    actions = ("revoke_keys",)

    def get_readonly_fields(self, request, obj=None):
        """Hide the one-time secret and key id on the add form.

        A new key has no id or secret until it is saved, so showing empty
        placeholders there would only confuse; they appear on the change page
        right after creation.
        """
        fields = list(super().get_readonly_fields(request, obj))
        if obj is None:
            for name in ("key_id", "one_time_secret", "last_used", "created_at", "revoked_at"):
                fields.remove(name)
        return tuple(fields)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("label", "sponsor", "created_by", "active", "expires_at")
        return self.fields

    def save_model(self, request, obj, form, change):
        """Mint the id+secret on first save.

        `key_hash` is never part of the form, so the only way a key comes into
        existence is through this method; the plaintext is stashed on the
        instance purely for `one_time_secret` to reveal once.
        """
        if not change and not obj.pk:
            from .models import API_KEY_SEPARATOR, generate_api_key

            key_id, presented = generate_api_key()
            _, secret = presented.split(API_KEY_SEPARATOR, 1)
            obj.key_id = key_id
            obj.key_hash = make_password(secret)
            obj._one_time_secret = presented
            if obj.created_by_id is None:
                obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="API key (shown once, copy it now)")
    def one_time_secret(self, obj):
        secret = getattr(obj, "_one_time_secret", None)
        if not secret:
            return "—"
        return format_html("<code>{}</code>", secret)

    @admin.action(description="Revoke selected API keys")
    def revoke_keys(self, request, queryset):
        for key in queryset:
            key.revoke()
