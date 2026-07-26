from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("email", "username", "display_name", "is_staff")
    search_fields = ("email", "username", "display_name")
    ordering = ("email",)
    fieldsets = UserAdmin.fieldsets + (("Profile", {"fields": ("display_name", "pronouns", "bio")}),)
