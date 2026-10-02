from django.db import models


class Category(models.Model):
    """
    Classifies inventory items into broad types (e.g., Canned Goods, Dry Grains,
    Hygiene Kits, Bedding, Medical Supplies).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the inventory category (e.g., 'Non-Perishable Food', 'Baby Care')."
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of goods falling under this category."
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    """
    Catalog representation of an item tracked by an organization.
    
    NOTE (Phase 1 Scope): This model acts as the core product definition/catalog.
    Stock quantities, batch expiration dates, warehouse locations, and transaction logs
    are intentionally reserved for Phase 2.
    """

    name = models.CharField(
        max_length=200,
        help_text="Common name of the item (e.g., 'Long Grain White Rice', 'Bottled Water 500ml')."
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='items',
        help_text="Category classification for this item. PROTECT prevents accidental orphan items."
    )
    unit_of_measure = models.CharField(
        max_length=50,
        help_text="Standard unit used to track this item (e.g., 'kg', 'pieces', 'liters', 'boxes')."
    )
    is_perishable = models.BooleanField(
        default=False,
        help_text="Designates whether the item requires climate control or expires rapidly."
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='inventory_items',
        help_text="The shelter or food bank managing this inventory item definition."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this item definition was created in the system."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this item definition was last modified."
    )

    class Meta:
        ordering = ['organization', 'name']
        verbose_name = 'Inventory Item'
        verbose_name_plural = 'Inventory Items'
        # An organization shouldn't duplicate exact item names within its own catalog
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'],
                name='unique_item_per_organization'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.name}) - [{self.unit_of_measure}]"
