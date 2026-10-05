from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin configuration for the custom User model.
    Extends standard Django UserAdmin with ReliefStock role, phone, and organization fields.
    """

    list_display = (
        "username",
        "email",
        "role",
        "organization",
        "phone_number",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "role",
        "organization",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "organization__name",
    )
    ordering = ("username",)

    # Add custom fields to change form
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            _("ReliefStock Role & Organization"),
            {
                "fields": ("role", "organization", "phone_number"),
            },
        ),
    )

    # Add custom fields to create/add user form
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            _("ReliefStock Profile Details"),
            {
                "classes": ("wide",),
                "fields": ("role", "organization", "phone_number"),
            },
        ),
    )
