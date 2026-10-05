from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from inventory.models import (
    Category,
    DistributionRequest,
    DistributionRequestItem,
    Donation,
    InventoryItem,
    StockTransaction,
)


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for item categories."""

    class Meta:
        model = Category
        fields = ["id", "name", "description"]


class InventoryItemSerializer(serializers.ModelSerializer):
    """
    Serializer for inventory catalog items including dynamic live stock counts
    and low-stock threshold alerts.
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    current_stock = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "unit_of_measure",
            "is_perishable",
            "reorder_threshold",
            "current_stock",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_current_stock(self, obj):
        # Use annotated current_stock if present, else fallback to model method
        stock = getattr(obj, "current_stock", None)
        if stock is not None:
            return Decimal(str(stock))
        return obj.get_current_stock()

    def get_is_low_stock(self, obj):
        return obj.is_low_stock

    def validate_category(self, value):
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["organization"] = request.user.organization
        return super().create(validated_data)


class StockTransactionSerializer(serializers.ModelSerializer):
    """Read-only serializer for individual stock ledger movements."""

    inventory_item_name = serializers.CharField(source="inventory_item.name", read_only=True)
    recorded_by_username = serializers.CharField(source="recorded_by.username", read_only=True)
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )

    class Meta:
        model = StockTransaction
        fields = [
            "id",
            "inventory_item",
            "inventory_item_name",
            "transaction_type",
            "transaction_type_display",
            "quantity",
            "expiry_date",
            "note",
            "recorded_by",
            "recorded_by_username",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class DonationItemInputSerializer(serializers.Serializer):
    """Input serializer for line items within a donation submission."""

    inventory_item = serializers.PrimaryKeyRelatedField(queryset=InventoryItem.objects.all())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    expiry_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class DonationSerializer(serializers.ModelSerializer):
    """
    Serializer for Donation events.
    Supports atomic multi-item creation of donations and child StockTransactions.
    """

    recorded_by_username = serializers.CharField(source="recorded_by.username", read_only=True)
    donor_username = serializers.CharField(
        source="donor_user.username", read_only=True, default=None
    )
    items = DonationItemInputSerializer(many=True, write_only=True, required=False)
    stock_transactions = StockTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Donation
        fields = [
            "id",
            "donor_name",
            "donor_contact",
            "donor_user",
            "donor_username",
            "date_received",
            "notes",
            "recorded_by",
            "recorded_by_username",
            "items",
            "stock_transactions",
            "created_at",
        ]
        read_only_fields = ["recorded_by", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user_org = getattr(request.user, "organization", None)

        # Validate that items belong to user's organization
        items_data = attrs.get("items", [])
        for item_data in items_data:
            item = item_data["inventory_item"]
            if user_org and item.organization_id != user_org.id:
                raise serializers.ValidationError(
                    f"Item '{item.name}' does not belong to your organization."
                )
            if item.is_perishable and not item_data.get("expiry_date"):
                # Note: Optional warning, but per Phase 2 business rules perishables should track expiry
                pass

        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context.get("request")
        user_org = request.user.organization

        with transaction.atomic():
            donation = Donation.objects.create(
                organization=user_org, recorded_by=request.user, **validated_data
            )

            for item_data in items_data:
                StockTransaction.objects.create(
                    inventory_item=item_data["inventory_item"],
                    organization=user_org,
                    transaction_type=StockTransaction.TransactionType.DONATION_IN,
                    quantity=item_data["quantity"],
                    donation=donation,
                    expiry_date=item_data.get("expiry_date"),
                    note=item_data.get("note", ""),
                    recorded_by=request.user,
                )

        return donation


class DistributionRequestItemSerializer(serializers.ModelSerializer):
    """Serializer for individual items in a distribution request."""

    inventory_item_name = serializers.CharField(source="inventory_item.name", read_only=True)
    unit_of_measure = serializers.CharField(source="inventory_item.unit_of_measure", read_only=True)
    quantity_remaining = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_fully_fulfilled = serializers.BooleanField(read_only=True)

    class Meta:
        model = DistributionRequestItem
        fields = [
            "id",
            "inventory_item",
            "inventory_item_name",
            "unit_of_measure",
            "quantity_requested",
            "quantity_fulfilled",
            "quantity_remaining",
            "is_fully_fulfilled",
        ]
        read_only_fields = ["quantity_fulfilled"]


class DistributionRequestItemInputSerializer(serializers.Serializer):
    """Input serializer for requesting line items."""

    inventory_item = serializers.PrimaryKeyRelatedField(queryset=InventoryItem.objects.all())
    quantity_requested = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )


class DistributionRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for client distribution requests.
    Supports atomic creation of requests with multiple items.
    """

    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=None
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items = DistributionRequestItemInputSerializer(many=True, write_only=True, required=False)
    request_items = DistributionRequestItemSerializer(source="items", many=True, read_only=True)

    class Meta:
        model = DistributionRequest
        fields = [
            "id",
            "recipient_name",
            "recipient_contact",
            "notes",
            "status",
            "status_display",
            "requested_at",
            "reviewed_at",
            "requested_by",
            "requested_by_username",
            "reviewed_by",
            "reviewed_by_username",
            "items",
            "request_items",
        ]
        read_only_fields = [
            "status",
            "status_display",
            "requested_at",
            "reviewed_at",
            "requested_by",
            "reviewed_by",
        ]

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one item must be included in the distribution request."
            )

        seen_item_ids = set()
        request = self.context.get("request")
        user_org = getattr(request.user, "organization", None)

        for item_data in value:
            item = item_data["inventory_item"]
            if item.id in seen_item_ids:
                raise serializers.ValidationError(
                    f"Item '{item.name}' cannot be listed more than once in the same request."
                )
            seen_item_ids.add(item.id)

            if user_org and item.organization_id != user_org.id:
                raise serializers.ValidationError(
                    f"Item '{item.name}' does not belong to your organization."
                )

        return value

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context.get("request")
        user_org = request.user.organization

        with transaction.atomic():
            dist_request = DistributionRequest.objects.create(
                organization=user_org,
                requested_by=request.user,
                status=DistributionRequest.Status.PENDING,
                **validated_data,
            )

            for item_data in items_data:
                DistributionRequestItem.objects.create(
                    distribution_request=dist_request,
                    inventory_item=item_data["inventory_item"],
                    quantity_requested=item_data["quantity_requested"],
                    quantity_fulfilled=Decimal("0.00"),
                )

        return dist_request


class DistributionReviewSerializer(serializers.Serializer):
    """Input serializer for approving or rejecting a distribution request."""

    action = serializers.ChoiceField(choices=["APPROVE", "REJECT"])
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["action"] == "REJECT" and not attrs.get("notes", "").strip():
            raise serializers.ValidationError(
                {"notes": "A reason note is required when rejecting a distribution request."}
            )
        return attrs


class FulfillItemInputSerializer(serializers.Serializer):
    """Input serializer for a single item dispatch during fulfillment."""

    item_id = serializers.IntegerField()
    quantity_to_fulfill = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )


class DistributionFulfillSerializer(serializers.Serializer):
    """Input serializer for partial or complete fulfillment of an approved request."""

    notes = serializers.CharField(required=False, allow_blank=True, default="")
    dispatches = FulfillItemInputSerializer(many=True)

    def validate_dispatches(self, value):
        if not value:
            raise serializers.ValidationError("At least one dispatch quantity must be provided.")
        return value


class DashboardMetricsSerializer(serializers.Serializer):
    """Read-only serializer representing executive dashboard metrics."""

    organization_name = serializers.CharField()
    today = serializers.DateField()
    total_distinct_items = serializers.IntegerField()
    total_stock_units = serializers.DecimalField(max_digits=14, decimal_places=2)
    low_stock_count = serializers.IntegerField()
    expiring_soon_count = serializers.IntegerField()
    expired_count = serializers.IntegerField()
    pending_requests_count = serializers.IntegerField()
    donations_this_month_count = serializers.IntegerField()
    items_donated_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    distributions_this_month_count = serializers.IntegerField()
    items_distributed_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
