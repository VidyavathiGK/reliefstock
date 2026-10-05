from django.contrib import admin

from .models import (
    Category,
    DistributionRequest,
    DistributionRequestItem,
    Donation,
    InventoryItem,
    StockTransaction,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    Admin configuration for item categories.
    """

    list_display = ("name", "description")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    """
    Admin configuration for inventory catalog items.
    """

    list_display = (
        "name",
        "category",
        "organization",
        "display_current_stock",
        "reorder_threshold",
        "unit_of_measure",
        "is_perishable",
        "created_at",
    )
    list_filter = (
        "is_perishable",
        "category",
        "organization",
        "created_at",
    )
    search_fields = (
        "name",
        "category__name",
        "organization__name",
    )
    list_select_related = ("category", "organization")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("organization", "name")

    @admin.display(description="Current Stock")
    def display_current_stock(self, obj):
        return f"{obj.get_current_stock()} {obj.unit_of_measure}"


class StockTransactionInline(admin.TabularInline):
    """
    Inline representation of stock transactions inside a donation admin view.
    """

    model = StockTransaction
    extra = 0
    fields = ("inventory_item", "quantity", "expiry_date", "note", "recorded_by")
    readonly_fields = ("created_at",)


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    """
    Admin configuration for recorded donations.
    """

    list_display = (
        "id",
        "donor_display",
        "donor_user",
        "organization",
        "date_received",
        "recorded_by",
        "total_items_count",
        "created_at",
    )
    list_filter = (
        "organization",
        "date_received",
        "created_at",
    )
    search_fields = (
        "donor_name",
        "donor_contact",
        "donor_user__username",
        "notes",
        "recorded_by__username",
    )
    list_select_related = ("organization", "recorded_by", "donor_user")
    readonly_fields = ("created_at",)
    inlines = [StockTransactionInline]

    @admin.display(description="Donor")
    def donor_display(self, obj):
        return obj.donor_name if obj.donor_name else "Anonymous"

    @admin.display(description="Items Count")
    def total_items_count(self, obj):
        return obj.stock_transactions.count()


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    """
    Admin configuration for stock transaction ledger.
    """

    list_display = (
        "created_at",
        "inventory_item",
        "transaction_type",
        "quantity_display",
        "organization",
        "recorded_by",
        "donation",
        "distribution_request",
        "expiry_date",
    )
    list_filter = (
        "organization",
        "transaction_type",
        "created_at",
        "inventory_item__category",
    )
    search_fields = (
        "inventory_item__name",
        "note",
        "recorded_by__username",
        "donation__donor_name",
        "distribution_request__recipient_name",
    )
    list_select_related = (
        "inventory_item",
        "organization",
        "recorded_by",
        "donation",
        "distribution_request",
    )
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(description="Quantity Moved")
    def quantity_display(self, obj):
        sign = (
            "+"
            if obj.transaction_type
            in [
                StockTransaction.TransactionType.DONATION_IN,
                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
            ]
            else "-"
        )
        return f"{sign}{obj.quantity} {obj.inventory_item.unit_of_measure}"


class DistributionRequestItemInline(admin.TabularInline):
    """
    Inline list of requested items inside the distribution request admin view.
    """

    model = DistributionRequestItem
    extra = 0
    fields = ("inventory_item", "quantity_requested", "quantity_fulfilled")


@admin.register(DistributionRequest)
class DistributionRequestAdmin(admin.ModelAdmin):
    """
    Admin configuration for distribution requests.
    """

    list_display = (
        "id",
        "recipient_name",
        "organization",
        "status",
        "requested_by",
        "requested_at",
        "reviewed_by",
        "reviewed_at",
        "items_count",
    )
    list_filter = (
        "status",
        "organization",
        "requested_at",
        "reviewed_at",
    )
    search_fields = (
        "recipient_name",
        "recipient_contact",
        "notes",
        "requested_by__username",
        "reviewed_by__username",
    )
    list_select_related = ("organization", "requested_by", "reviewed_by")
    readonly_fields = ("requested_at", "reviewed_at")
    inlines = [DistributionRequestItemInline]

    @admin.display(description="Line Items")
    def items_count(self, obj):
        return obj.items.count()


@admin.register(DistributionRequestItem)
class DistributionRequestItemAdmin(admin.ModelAdmin):
    """
    Admin configuration for individual distribution request line items.
    """

    list_display = (
        "id",
        "distribution_request",
        "inventory_item",
        "quantity_requested",
        "quantity_fulfilled",
    )
    list_filter = (
        "distribution_request__status",
        "distribution_request__organization",
    )
    search_fields = (
        "inventory_item__name",
        "distribution_request__recipient_name",
    )
    list_select_related = ("distribution_request", "inventory_item")
