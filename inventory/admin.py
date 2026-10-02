from django.contrib import admin
from .models import Category, InventoryItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    Admin configuration for item categories.
    """

    list_display = ('name', 'description')
    search_fields = ('name', 'description')
    ordering = ('name',)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    """
    Admin configuration for inventory catalog items.
    """

    list_display = (
        'name',
        'category',
        'organization',
        'unit_of_measure',
        'is_perishable',
        'created_at',
    )
    list_filter = (
        'is_perishable',
        'category',
        'organization',
        'created_at',
    )
    search_fields = (
        'name',
        'category__name',
        'organization__name',
    )
    list_select_related = ('category', 'organization')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('organization', 'name')
