from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Category(models.Model):
    """
    Classifies inventory items into broad types (e.g., Canned Goods, Dry Grains,
    Hygiene Kits, Bedding, Medical Supplies).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the inventory category (e.g., 'Non-Perishable Food', 'Baby Care').",
    )
    description = models.TextField(
        blank=True, help_text="Detailed description of goods falling under this category."
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    """
    Catalog representation of an item tracked by an organization.

    Current stock is calculated dynamically from the immutable ledger of
    StockTransaction records to guarantee audit integrity without cache drift.
    """

    name = models.CharField(
        max_length=200,
        help_text="Common name of the item (e.g., 'Long Grain White Rice', 'Bottled Water 500ml').",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="items",
        help_text="Category classification for this item. PROTECT prevents accidental orphan items.",
    )
    unit_of_measure = models.CharField(
        max_length=50,
        help_text="Standard unit used to track this item (e.g., 'kg', 'pieces', 'liters', 'boxes').",
    )
    is_perishable = models.BooleanField(
        default=False,
        help_text="Designates whether the item requires climate control or expires rapidly.",
    )
    reorder_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Minimum stock level before alerting staff to reorder or request donations.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="inventory_items",
        help_text="The shelter or food bank managing this inventory item definition.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this item definition was created in the system.",
    )
    updated_at = models.DateTimeField(
        auto_now=True, help_text="Timestamp when this item definition was last modified."
    )

    class Meta:
        ordering = ["organization", "name"]
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        # An organization shouldn't duplicate exact item names within its own catalog
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="unique_item_per_organization"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.name}) - [{self.unit_of_measure}]"

    def get_current_stock(self) -> Decimal:
        """
        Calculates the real-time stock balance from the transaction ledger:
        Stock = (SUM(IN) - SUM(OUT))
        """
        aggregates = self.stock_transactions.aggregate(
            total_in=models.Sum(
                "quantity",
                filter=models.Q(
                    transaction_type__in=[
                        StockTransaction.TransactionType.DONATION_IN,
                        StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                    ]
                ),
            ),
            total_out=models.Sum(
                "quantity",
                filter=models.Q(
                    transaction_type__in=[
                        StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                        StockTransaction.TransactionType.DISTRIBUTION_OUT,
                    ]
                ),
            ),
        )
        total_in = aggregates["total_in"] or Decimal("0.00")
        total_out = aggregates["total_out"] or Decimal("0.00")
        return total_in - total_out

    @property
    def is_low_stock(self) -> bool:
        """Returns True if reorder_threshold is set and current stock is at or below it."""
        if self.reorder_threshold is None:
            return False
        return self.get_current_stock() <= self.reorder_threshold


class Donation(models.Model):
    """
    Records an incoming donation drop-off event.

    A donation can contain one or more items, linked via child StockTransaction
    records of type DONATION_IN.
    """

    donor_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the donor or contributing group (leave blank if anonymous).",
    )
    donor_contact = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional contact information (email, phone, or address) for receipts.",
    )
    donor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations_made",
        help_text="Optional link to a registered User account with the DONOR role.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="donations",
        help_text="The organization that received this donation.",
    )
    date_received = models.DateField(
        default=timezone.now,
        help_text="Calendar date when the donation was physically handed over.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_donations",
        help_text="Staff or volunteer member who processed this intake.",
    )
    notes = models.TextField(
        blank=True, help_text="Optional intake details, condition of packaging, or vehicle info."
    )
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="System audit timestamp when this record was logged."
    )

    class Meta:
        ordering = ["-date_received", "-created_at"]
        verbose_name = "Donation"
        verbose_name_plural = "Donations"

    def __str__(self):
        display_name = self.donor_name if self.donor_name else "Anonymous Donor"
        return f"Donation #{self.pk} by {display_name} on {self.date_received}"


class DistributionRequest(models.Model):
    """
    Formal request to distribute inventory items from an organization's stock
    to a client, family, shelter resident, or community program.

    Follows a multi-tier governance workflow:
    PENDING -> APPROVED / REJECTED -> FULFILLED (full or partial)
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        APPROVED = "APPROVED", "Approved for Fulfillment"
        REJECTED = "REJECTED", "Rejected"
        FULFILLED = "FULFILLED", "Fulfilled"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="distribution_requests",
        help_text="The organization whose inventory is being requested.",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="distribution_requests",
        help_text="Staff or volunteer who submitted this request on behalf of the recipient.",
    )
    recipient_name = models.CharField(
        max_length=255,
        help_text="Name of the individual, family, shelter client, or community program receiving items.",
    )
    recipient_contact = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional phone number, email, or emergency contact info.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current state in the approval and fulfillment lifecycle.",
    )
    requested_at = models.DateTimeField(
        auto_now_add=True, help_text="Timestamp when this distribution request was submitted."
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when an administrator approved or rejected the request.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_distribution_requests",
        help_text="Administrator who approved or rejected this request.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Context regarding recipient needs, rejection reasons, or partial fulfillment notes.",
    )

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = "Distribution Request"
        verbose_name_plural = "Distribution Requests"

    def __str__(self):
        return f"Request #{self.pk} for {self.recipient_name} [{self.get_status_display()}]"

    def clean(self):
        super().clean()
        if self.requested_by_id and self.organization_id:
            user_org = self.requested_by.organization_id
            if user_org and user_org != self.organization_id:
                raise ValidationError(
                    {
                        "requested_by": "Requesting user's organization does not match the request organization."
                    }
                )
        if self.reviewed_by_id and self.organization_id:
            rev_org = self.reviewed_by.organization_id
            if rev_org and rev_org != self.organization_id and not self.reviewed_by.is_superuser:
                raise ValidationError(
                    {
                        "reviewed_by": "Reviewing admin's organization does not match the request organization."
                    }
                )


class DistributionRequestItem(models.Model):
    """
    Line item inside a DistributionRequest specifying the desired inventory item
    and quantities (requested vs fulfilled).
    """

    distribution_request = models.ForeignKey(
        DistributionRequest,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="The parent distribution request.",
    )
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="distribution_items",
        help_text="The item to be distributed.",
    )
    quantity_requested = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Quantity requested for the recipient.",
    )
    quantity_fulfilled = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Actual quantity fulfilled/dispatched.",
    )

    class Meta:
        ordering = ["inventory_item__name"]
        verbose_name = "Distribution Request Item"
        verbose_name_plural = "Distribution Request Items"
        constraints = [
            models.UniqueConstraint(
                fields=["distribution_request", "inventory_item"],
                name="unique_item_per_distribution_request",
            )
        ]

    def __str__(self):
        fulfilled = (
            self.quantity_fulfilled if self.quantity_fulfilled is not None else Decimal("0.00")
        )
        return (
            f"{self.inventory_item.name}: {fulfilled}/{self.quantity_requested} "
            f"{self.inventory_item.unit_of_measure}"
        )

    def clean(self):
        super().clean()
        if self.quantity_requested is not None and self.quantity_requested <= Decimal("0.00"):
            raise ValidationError(
                {"quantity_requested": "Requested quantity must be greater than zero."}
            )

        if self.quantity_fulfilled is not None and self.quantity_fulfilled < Decimal("0.00"):
            raise ValidationError({"quantity_fulfilled": "Fulfilled quantity cannot be negative."})

        if self.distribution_request_id and self.inventory_item_id:
            if self.distribution_request.organization_id != self.inventory_item.organization_id:
                raise ValidationError(
                    {
                        "inventory_item": (
                            f"Item '{self.inventory_item.name}' belongs to organization "
                            f"'{self.inventory_item.organization.name}', but request belongs to "
                            f"'{self.distribution_request.organization.name}'."
                        )
                    }
                )

    @property
    def quantity_remaining(self) -> Decimal:
        """Returns the unfulfilled quantity remaining for this line item."""
        fulfilled = self.quantity_fulfilled or Decimal("0.00")
        return max(Decimal("0.00"), self.quantity_requested - fulfilled)

    @property
    def is_fully_fulfilled(self) -> bool:
        """Checks if line item is completely fulfilled."""
        fulfilled = self.quantity_fulfilled or Decimal("0.00")
        return fulfilled >= self.quantity_requested


class StockTransaction(models.Model):
    """
    Immutable audit ledger recording every inflow or outflow of inventory items.

    Stock quantities are strictly derived by summing these transaction records.
    """

    class TransactionType(models.TextChoices):
        DONATION_IN = "DONATION_IN", "Donation Received (In)"
        MANUAL_ADJUSTMENT_IN = "MANUAL_ADJUSTMENT_IN", "Manual Adjustment (In)"
        MANUAL_ADJUSTMENT_OUT = "MANUAL_ADJUSTMENT_OUT", "Manual Adjustment (Out)"
        # Reserved for Phase 3 distribution workflow
        DISTRIBUTION_OUT = "DISTRIBUTION_OUT", "Distribution to Client (Out)"

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="stock_transactions",
        help_text="The catalog item being added or deducted.",
    )
    transaction_type = models.CharField(
        max_length=30, choices=TransactionType.choices, help_text="Nature of the stock movement."
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Positive quantity moved in this transaction.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_stock_transactions",
        help_text="User who authorized or performed this stock action.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="stock_transactions",
        help_text="The organization owning the item and facility.",
    )
    donation = models.ForeignKey(
        Donation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
        help_text="Linked donation event if this transaction originated from a donation.",
    )
    distribution_request = models.ForeignKey(
        DistributionRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
        help_text="Linked distribution request if this transaction represents an outbound distribution.",
    )
    note = models.TextField(
        blank=True,
        help_text="Explanation for adjustments, damages, or discrepancies (mandatory for manual adjustments).",
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expiration date (applicable only if the item is marked perishable).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Exact audit timestamp of transaction."
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Stock Transaction"
        verbose_name_plural = "Stock Transactions"

    def __str__(self):
        sign = (
            "+"
            if self.transaction_type
            in [self.TransactionType.DONATION_IN, self.TransactionType.MANUAL_ADJUSTMENT_IN]
            else "-"
        )
        return (
            f"[{self.get_transaction_type_display()}] {sign}{self.quantity} "
            f"{self.inventory_item.unit_of_measure} of {self.inventory_item.name}"
        )

    def clean(self):
        super().clean()

        # 1. Quantity must be strictly positive
        if self.quantity is not None and self.quantity <= Decimal("0.00"):
            raise ValidationError({"quantity": "Transaction quantity must be greater than zero."})

        # 2. Organization consistency between item and transaction
        if self.inventory_item_id and self.organization_id:
            if self.inventory_item.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "organization": (
                            f"Transaction organization ({self.organization.name}) does not match "
                            f"the item's organization ({self.inventory_item.organization.name})."
                        )
                    }
                )

        # 3. Organization consistency with donation and distribution_request (if present)
        if self.donation_id and self.organization_id:
            if self.donation.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "donation": (
                            f"Donation organization ({self.donation.organization.name}) does not match "
                            f"the transaction organization ({self.organization.name})."
                        )
                    }
                )

        if self.distribution_request_id and self.organization_id:
            if self.distribution_request.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "distribution_request": (
                            f"Distribution request organization ({self.distribution_request.organization.name}) does not match "
                            f"the transaction organization ({self.organization.name})."
                        )
                    }
                )

        # 4. Mandatory note for manual adjustments
        is_manual = self.transaction_type in [
            self.TransactionType.MANUAL_ADJUSTMENT_IN,
            self.TransactionType.MANUAL_ADJUSTMENT_OUT,
        ]
        if is_manual and not (self.note and self.note.strip()):
            raise ValidationError(
                {"note": "A note explaining the reason is required for manual stock adjustments."}
            )

        # 5. Expiry date valid only for perishable items
        if self.expiry_date and self.inventory_item_id and not self.inventory_item.is_perishable:
            raise ValidationError(
                {
                    "expiry_date": f"Item '{self.inventory_item.name}' is not marked as perishable. Expiry date should not be set."
                }
            )

        # 6. Prevent negative stock from outbound movements
        if (
            self.transaction_type
            in [self.TransactionType.MANUAL_ADJUSTMENT_OUT, self.TransactionType.DISTRIBUTION_OUT]
            and self.inventory_item_id
            and self.quantity
        ):
            current_stock = self.inventory_item.get_current_stock()
            # If editing an existing reduction transaction, credit back its previous amount
            if self.pk:
                try:
                    orig = StockTransaction.objects.get(pk=self.pk)
                    if orig.transaction_type in [
                        self.TransactionType.MANUAL_ADJUSTMENT_OUT,
                        self.TransactionType.DISTRIBUTION_OUT,
                    ]:
                        current_stock += orig.quantity
                except StockTransaction.DoesNotExist:
                    pass

            if self.quantity > current_stock:
                raise ValidationError(
                    {
                        "quantity": (
                            f"Cannot deduct {self.quantity} {self.inventory_item.unit_of_measure}. "
                            f"Current available stock is only {current_stock} {self.inventory_item.unit_of_measure}."
                        )
                    }
                )
