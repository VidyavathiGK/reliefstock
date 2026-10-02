from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """
    Admin configuration for community relief organizations.
    """

    list_display = (
        'name',
        'org_type',
        'contact_email',
        'contact_phone',
        'created_at',
    )
    list_filter = (
        'org_type',
        'created_at',
    )
    search_fields = (
        'name',
        'contact_email',
        'contact_phone',
        'address',
    )
    ordering = ('name',)
    readonly_fields = ('created_at',)
