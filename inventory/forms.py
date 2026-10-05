from decimal import Decimal

from django import forms
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from .models import (
    DistributionRequest,
    Donation,
    InventoryItem,
    StockTransaction,
)


class DonationHeaderForm(forms.ModelForm):
    """
    Form for recording the high-level donor details and drop-off metadata.
    """

    date_received = forms.DateField(
        initial=timezone.now,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Date the donation was received.",
    )

    class Meta:
        model = Donation
        fields = ["donor_name", "donor_contact", "donor_user", "date_received", "notes"]
        widgets = {
            "donor_name": forms.TextInput(
                attrs={
                    "placeholder": "e.g., Local Rotary Club or John Doe (leave blank if anonymous)"
                }
            ),
            "donor_contact": forms.TextInput(
                attrs={"placeholder": "e.g., phone or email for tax receipt"}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Optional drop-off notes or condition details"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import User

        self.fields["donor_user"].queryset = User.objects.filter(role=User.Role.DONOR)
        self.fields["donor_user"].required = False
        self.fields["donor_user"].empty_label = "-- None / Anonymous / External Donor --"
        self.fields["donor_user"].label = "Registered Donor Account (optional)"
        self.fields[
            "donor_user"
        ].help_text = (
            "Link this donation to a registered donor user account so they can view receipts."
        )


class DonationItemLineForm(forms.Form):
    """
    Form representing a single item row in a multi-item donation intake.
    """

    inventory_item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.none(),
        required=False,
        empty_label="-- Select an Item --",
        label="Item",
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "Quantity"}),
        label="Quantity",
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Expiry Date (perishables)",
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Optional line note (e.g. batch or crate #)"}),
        label="Line Note",
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["inventory_item"].queryset = InventoryItem.objects.filter(
                organization=organization
            ).select_related("category")

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get("inventory_item")
        quantity = cleaned_data.get("quantity")
        expiry_date = cleaned_data.get("expiry_date")

        # If both item and quantity are empty, row is considered blank/skipped
        if not item and not quantity:
            return cleaned_data

        # If one is present, both must be present
        if item and not quantity:
            self.add_error("quantity", "Quantity is required for selected item.")
        if quantity and not item:
            self.add_error("inventory_item", "Please select an item for this quantity.")

        # Validate perishable rule for expiry date
        if item and expiry_date and not item.is_perishable:
            self.add_error(
                "expiry_date",
                f"'{item.name}' is not marked as perishable. Expiry date should only be provided for perishable items.",
            )

        return cleaned_data


class BaseDonationItemFormSet(BaseFormSet):
    """
    FormSet validator ensuring at least one valid item is entered and preventing
    duplicate items in the same donation submission.
    """

    def clean(self):
        if any(self.errors):
            return

        valid_items_count = 0
        seen_items = set()

        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue

            item = form.cleaned_data.get("inventory_item")
            quantity = form.cleaned_data.get("quantity")

            if item and quantity:
                valid_items_count += 1
                if item.id in seen_items:
                    form.add_error(
                        "inventory_item",
                        f"'{item.name}' was selected more than once. Please combine the quantities into one entry.",
                    )
                seen_items.add(item.id)

        if valid_items_count == 0:
            raise forms.ValidationError(
                "You must record at least one item with a valid quantity in this donation."
            )


# Formset factory creating 5 item lines by default for fast multi-item intake
DonationItemFormSet = formset_factory(
    DonationItemLineForm, formset=BaseDonationItemFormSet, extra=5, can_delete=False
)


class ManualStockAdjustmentForm(forms.Form):
    """
    Form allowing staff to manually adjust stock upwards or downwards.
    Requires an explicit explanation note for audit compliance.
    """

    TRANSACTION_CHOICES = [
        (StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN, "Manual Stock Addition (+)"),
        (
            StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
            "Manual Stock Deduction / Shrinkage (-)",
        ),
    ]

    transaction_type = forms.ChoiceField(
        choices=TRANSACTION_CHOICES, widget=forms.RadioSelect, label="Adjustment Type"
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        label="Adjustment Quantity",
        help_text="Enter a positive number. Deduction or addition is determined by the adjustment type.",
    )
    note = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Explain why this adjustment is needed (e.g. damaged goods, audit discrepancy, expired stock)...",
            }
        ),
        required=True,
        label="Audit Reason / Note",
        help_text="Required explanation for internal tracking.",
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Expiry Date (if adding perishable items)",
        help_text="Only applicable for inbound adjustments on perishable items.",
    )

    def __init__(self, *args, inventory_item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory_item = inventory_item

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get("transaction_type")
        quantity = cleaned_data.get("quantity")
        expiry_date = cleaned_data.get("expiry_date")
        item = self.inventory_item

        if not item or not quantity or not transaction_type:
            return cleaned_data

        # Check perishable constraint
        if expiry_date and not item.is_perishable:
            self.add_error(
                "expiry_date",
                f"'{item.name}' is not marked as perishable. Expiry date cannot be set.",
            )

        # Validate that deductions do not exceed available current stock
        if transaction_type == StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT:
            current_stock = item.get_current_stock()
            if quantity > current_stock:
                self.add_error(
                    "quantity",
                    f"Cannot deduct {quantity} {item.unit_of_measure}. Current stock is only {current_stock} {item.unit_of_measure}.",
                )

        return cleaned_data


class DistributionRequestHeaderForm(forms.ModelForm):
    """
    Form for capturing client/recipient information and request notes.
    """

    class Meta:
        model = DistributionRequest
        fields = ["recipient_name", "recipient_contact", "notes"]
        widgets = {
            "recipient_name": forms.TextInput(
                attrs={"placeholder": "e.g., Jane Smith, Family of 4, or Shelter Resident"}
            ),
            "recipient_contact": forms.TextInput(
                attrs={"placeholder": "e.g., Phone number or client case ID"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Optional context regarding recipient needs or dispatch requirements",
                }
            ),
        }


class DistributionRequestItemLineForm(forms.Form):
    """
    Form representing a single item row in a multi-item distribution request.
    """

    inventory_item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.none(),
        required=False,
        empty_label="-- Select an Item --",
        label="Item",
    )
    quantity_requested = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "Quantity"}),
        label="Quantity Requested",
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["inventory_item"].queryset = InventoryItem.objects.filter(
                organization=organization
            ).select_related("category")

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get("inventory_item")
        quantity = cleaned_data.get("quantity_requested")

        if not item and not quantity:
            return cleaned_data

        if item and not quantity:
            self.add_error("quantity_requested", "Quantity is required for selected item.")
        if quantity and not item:
            self.add_error("inventory_item", "Please select an item for this quantity.")

        return cleaned_data


class BaseDistributionRequestItemFormSet(BaseFormSet):
    """
    FormSet validator ensuring at least one valid item is entered and preventing
    duplicate items in the same distribution request.
    """

    def clean(self):
        if any(self.errors):
            return

        valid_items_count = 0
        seen_items = set()

        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue

            item = form.cleaned_data.get("inventory_item")
            quantity = form.cleaned_data.get("quantity_requested")

            if item and quantity:
                valid_items_count += 1
                if item.id in seen_items:
                    form.add_error(
                        "inventory_item",
                        f"'{item.name}' was selected more than once. Please combine the quantities into one entry.",
                    )
                seen_items.add(item.id)

        if valid_items_count == 0:
            raise forms.ValidationError(
                "You must specify at least one item with a valid quantity in this request."
            )


DistributionRequestItemFormSet = formset_factory(
    DistributionRequestItemLineForm,
    formset=BaseDistributionRequestItemFormSet,
    extra=5,
    can_delete=False,
)


class DistributionReviewForm(forms.Form):
    """
    Form allowing administrators to approve or reject a pending distribution request.
    """

    ACTION_CHOICES = [
        ("APPROVE", "Approve Request"),
        ("REJECT", "Reject Request"),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES, widget=forms.RadioSelect, label="Review Decision"
    )
    review_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Optional notes regarding approval or explanation for rejection...",
            }
        ),
        label="Review Notes / Rejection Reason",
    )


class DistributionFulfillmentForm(forms.Form):
    """
    Fulfillment form for dispatching approved distribution request items.
    Validates per-item fulfillment quantities against both remaining requested
    amounts and live stock on hand.
    """

    fulfillment_note = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Optional fulfillment / dispatch notes (e.g. batch or recipient sign-off)...",
            }
        ),
        label="Fulfillment Notes",
    )

    def __init__(self, *args, distribution_request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.distribution_request = distribution_request

        if distribution_request:
            for line_item in distribution_request.items.select_related("inventory_item").all():
                current_stock = line_item.inventory_item.get_current_stock()
                remaining = line_item.quantity_remaining
                # Pre-fill with the minimum of remaining and available stock, capped at >= 0
                suggested_qty = min(remaining, max(Decimal("0.00"), current_stock))

                field_name = f"fulfill_item_{line_item.id}"
                self.fields[field_name] = forms.DecimalField(
                    min_value=Decimal("0.00"),
                    max_digits=12,
                    decimal_places=2,
                    initial=suggested_qty,
                    widget=forms.NumberInput(
                        attrs={"step": "0.01", "min": "0.00", "class": "fulfill-qty-input"}
                    ),
                    label=f"{line_item.inventory_item.name} ({line_item.inventory_item.unit_of_measure})",
                    help_text=(
                        f"Requested: {line_item.quantity_requested} | "
                        f"Prev. Fulfilled: {line_item.quantity_fulfilled or 0} | "
                        f"Remaining: {remaining} | "
                        f"Current Stock: {current_stock}"
                    ),
                )

    def clean(self):
        cleaned_data = super().clean()
        if not self.distribution_request:
            return cleaned_data

        total_dispatching = Decimal("0.00")

        for line_item in self.distribution_request.items.select_related("inventory_item").all():
            field_name = f"fulfill_item_{line_item.id}"
            qty_to_dispatch = cleaned_data.get(field_name)

            if qty_to_dispatch is None:
                continue

            current_stock = line_item.inventory_item.get_current_stock()
            remaining = line_item.quantity_remaining

            if qty_to_dispatch > current_stock:
                self.add_error(
                    field_name,
                    f"Insufficient stock for '{line_item.inventory_item.name}'. Available: {current_stock} {line_item.inventory_item.unit_of_measure}, attempted to dispatch: {qty_to_dispatch}.",
                )

            if qty_to_dispatch > remaining:
                self.add_error(
                    field_name,
                    f"Cannot dispatch more than remaining requested amount ({remaining} {line_item.inventory_item.unit_of_measure}).",
                )

            total_dispatching += qty_to_dispatch

        if total_dispatching <= Decimal("0.00") and not self.errors:
            raise forms.ValidationError(
                "You must dispatch a positive quantity for at least one item."
            )

        return cleaned_data


class DateRangeReportFilterForm(forms.Form):
    """
    Filter form for report views supporting start/end date range and keyword search.
    """

    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Start Date"
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="End Date"
    )
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search by donor, recipient, notes..."}),
        label="Search Keyword",
    )
