from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.models import (
    Category,
    DistributionRequest,
    Donation,
    InventoryItem,
    StockTransaction,
)

from .permissions import (
    IsAdminOnly,
    IsStaffOrAdmin,
    IsStaffOrAdminOrDonorReadOnly,
    IsVolunteerOrStaff,
)
from .serializers import (
    CategorySerializer,
    DashboardMetricsSerializer,
    DistributionFulfillSerializer,
    DistributionRequestSerializer,
    DistributionReviewSerializer,
    DonationSerializer,
    InventoryItemSerializer,
    StockTransactionSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD API for item categories.
    Accessible to Staff and Admin users.
    """

    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsStaffOrAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name"]


class InventoryItemViewSet(viewsets.ModelViewSet):
    """
    CRUD API for catalog items with live stock annotations and alert filters.
    Strictly scoped to the requesting user's organization.
    """

    serializer_class = InventoryItemSerializer
    permission_classes = [IsStaffOrAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "category__name", "unit_of_measure"]
    ordering_fields = ["name", "category__name", "created_at"]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return InventoryItem.objects.none()

        org = getattr(user, "organization", None)
        if not org and user.is_superuser:
            from organizations.models import Organization

            org = Organization.objects.first()

        if not org:
            return InventoryItem.objects.none()

        return (
            InventoryItem.objects.filter(organization=org)
            .select_related("category")
            .annotate(
                current_stock=Coalesce(
                    Sum(
                        Case(
                            When(
                                stock_transactions__transaction_type__in=[
                                    StockTransaction.TransactionType.DONATION_IN,
                                    StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                                ],
                                then=F("stock_transactions__quantity"),
                            ),
                            When(
                                stock_transactions__transaction_type__in=[
                                    StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                                    StockTransaction.TransactionType.DISTRIBUTION_OUT,
                                ],
                                then=-F("stock_transactions__quantity"),
                            ),
                            output_field=DecimalField(),
                        )
                    ),
                    Value(Decimal("0.00"), output_field=DecimalField()),
                )
            )
            .order_by("category__name", "name")
        )

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """Returns items at or below their configured reorder threshold."""
        qs = self.get_queryset()
        low_stock_items = [
            item
            for item in qs
            if item.reorder_threshold is not None and item.current_stock <= item.reorder_threshold
        ]
        page = self.paginate_queryset(low_stock_items)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(low_stock_items, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def expiring_soon(self, request):
        """Returns perishable transactions expiring within the next 7 days."""
        user_org = self.request.user.organization
        today = timezone.localdate()
        seven_days = today + timedelta(days=7)

        txns = (
            StockTransaction.objects.filter(
                organization=user_org,
                inventory_item__is_perishable=True,
                expiry_date__gte=today,
                expiry_date__lte=seven_days,
            )
            .select_related("inventory_item", "recorded_by")
            .order_by("expiry_date")
        )

        page = self.paginate_queryset(txns)
        if page is not None:
            serializer = StockTransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = StockTransactionSerializer(txns, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def expired(self, request):
        """Returns perishable transactions already past their expiry date."""
        user_org = self.request.user.organization
        today = timezone.localdate()

        txns = (
            StockTransaction.objects.filter(
                organization=user_org, inventory_item__is_perishable=True, expiry_date__lt=today
            )
            .select_related("inventory_item", "recorded_by")
            .order_by("expiry_date")
        )

        page = self.paginate_queryset(txns)
        if page is not None:
            serializer = StockTransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = StockTransactionSerializer(txns, many=True)
        return Response(serializer.data)


class DonationViewSet(viewsets.ModelViewSet):
    """
    API for recording and viewing Donations.
    Staff/Volunteers see organization donations; Donors see only their personal history.
    """

    serializer_class = DonationSerializer
    permission_classes = [IsStaffOrAdminOrDonorReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["donor_name", "donor_contact", "notes"]
    ordering_fields = ["date_received", "created_at"]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Donation.objects.none()

        if user.role == "DONOR":
            return (
                Donation.objects.filter(
                    Q(donor_user=user)
                    | Q(donor_contact__iexact=user.email)
                    | Q(donor_name__iexact=user.username)
                )
                .select_related("organization")
                .prefetch_related("stock_transactions__inventory_item")
                .distinct()
                .order_by("-date_received", "-created_at")
            )

        org = getattr(user, "organization", None)
        if not org and user.is_superuser:
            from organizations.models import Organization

            org = Organization.objects.first()

        if not org:
            return Donation.objects.none()

        return (
            Donation.objects.filter(organization=org)
            .select_related("recorded_by", "donor_user")
            .prefetch_related("stock_transactions__inventory_item")
            .order_by("-date_received", "-created_at")
        )

    def create(self, request, *args, **kwargs):
        if request.user.role == "DONOR":
            return Response(
                {"detail": "Donors cannot record inbound warehouse donations."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)


class DistributionRequestViewSet(viewsets.ModelViewSet):
    """
    API for managing client distribution requests, admin review, and staff fulfillment.
    Multi-tenant isolation strictly enforced by organization.
    """

    serializer_class = DistributionRequestSerializer
    permission_classes = [IsVolunteerOrStaff]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["recipient_name", "recipient_contact", "notes"]
    ordering_fields = ["requested_at", "status"]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return DistributionRequest.objects.none()

        org = getattr(user, "organization", None)
        if not org and user.is_superuser:
            from organizations.models import Organization

            org = Organization.objects.first()

        if not org:
            return DistributionRequest.objects.none()

        return (
            DistributionRequest.objects.filter(organization=org)
            .select_related("requested_by", "reviewed_by")
            .prefetch_related("items__inventory_item")
            .order_by("-requested_at")
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAdminOnly])
    def review(self, request, pk=None):
        """Administrative review action: APPROVE or REJECT."""
        dist_request = self.get_object()
        if dist_request.status != DistributionRequest.Status.PENDING:
            return Response(
                {
                    "detail": f"Request cannot be reviewed in status '{dist_request.get_status_display()}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DistributionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action_type = (
            serializer.cleaned_data["action"]
            if hasattr(serializer, "cleaned_data")
            else serializer.validated_data["action"]
        )
        notes = serializer.validated_data.get("notes", "")

        if action_type == "APPROVE":
            dist_request.status = DistributionRequest.Status.APPROVED
            dist_request.reviewed_by = request.user
            dist_request.reviewed_at = timezone.now()
            if notes:
                dist_request.notes = f"{dist_request.notes}\n[Approval Note]: {notes}".strip()
            dist_request.save()
            return Response(
                {
                    "detail": "Distribution request approved successfully.",
                    "status": dist_request.status,
                },
                status=status.HTTP_200_OK,
            )
        else:
            dist_request.status = DistributionRequest.Status.REJECTED
            dist_request.reviewed_by = request.user
            dist_request.reviewed_at = timezone.now()
            dist_request.notes = f"{dist_request.notes}\n[Rejection Reason]: {notes}".strip()
            dist_request.save()
            return Response(
                {"detail": "Distribution request rejected.", "status": dist_request.status},
                status=status.HTTP_200_OK,
            )

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    def fulfill(self, request, pk=None):
        """Staff fulfillment action: atomically dispatches stock and creates StockTransactions."""
        dist_request = self.get_object()
        if dist_request.status not in [
            DistributionRequest.Status.APPROVED,
            DistributionRequest.Status.PENDING,
        ]:
            return Response(
                {
                    "detail": f"Cannot fulfill request in status '{dist_request.get_status_display()}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DistributionFulfillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dispatches = serializer.validated_data["dispatches"]
        user_notes = serializer.validated_data.get("notes", "")

        # Build map of items
        line_items = {
            item.id: item for item in dist_request.items.select_related("inventory_item").all()
        }

        # 1. Validation phase
        dispatch_plans = []
        for d in dispatches:
            item_id = d["item_id"]
            qty = d["quantity_to_fulfill"]

            if item_id not in line_items:
                return Response(
                    {"detail": f"Distribution line item ID {item_id} not found in this request."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            line_item = line_items[item_id]
            if qty > line_item.quantity_remaining:
                return Response(
                    {
                        "detail": f"Quantity {qty} exceeds remaining balance {line_item.quantity_remaining} for '{line_item.inventory_item.name}'."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            current_stock = line_item.inventory_item.get_current_stock()
            if qty > current_stock:
                return Response(
                    {
                        "detail": f"Insufficient live stock for '{line_item.inventory_item.name}'. Available: {current_stock}, requested: {qty}."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            dispatch_plans.append((line_item, qty))

        # 2. Execution phase (Atomic)
        with transaction.atomic():
            for line_item, qty in dispatch_plans:
                # Update line item fulfilled quantity
                line_item.quantity_fulfilled = (
                    line_item.quantity_fulfilled or Decimal("0.00")
                ) + qty
                line_item.save()

                # Deduct stock ledger
                StockTransaction.objects.create(
                    inventory_item=line_item.inventory_item,
                    organization=dist_request.organization,
                    transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
                    quantity=qty,
                    distribution_request=dist_request,
                    recorded_by=request.user,
                    note=f"API Dispatch for {dist_request.recipient_name}",
                )

            # Check if all items are fully satisfied
            all_fulfilled = all(
                (item.quantity_fulfilled or Decimal("0.00")) >= item.quantity_requested
                for item in line_items.values()
            )
            if all_fulfilled:
                dist_request.status = DistributionRequest.Status.FULFILLED
            else:
                dist_request.status = DistributionRequest.Status.APPROVED

            if user_notes:
                dist_request.notes = (
                    f"{dist_request.notes}\n[Fulfillment Note]: {user_notes}".strip()
                )

            dist_request.save()

        return Response(
            {
                "detail": "Fulfillment processed successfully.",
                "status": dist_request.status,
                "is_fully_fulfilled": all_fulfilled,
            },
            status=status.HTTP_200_OK,
        )


class DashboardAPIView(APIView):
    """
    Returns high-level live operational metrics for the requesting user's organization.
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request):
        user_org = request.user.organization
        today = timezone.localdate()
        seven_days = today + timedelta(days=7)

        # 1. Catalog & Stock aggregation
        item_qs = InventoryItem.objects.filter(organization=user_org)
        total_distinct_items = item_qs.count()

        annotated_items = item_qs.annotate(
            current_stock=Coalesce(
                Sum(
                    Case(
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.DONATION_IN,
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                            ],
                            then=F("stock_transactions__quantity"),
                        ),
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                                StockTransaction.TransactionType.DISTRIBUTION_OUT,
                            ],
                            then=-F("stock_transactions__quantity"),
                        ),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0.00"), output_field=DecimalField()),
            )
        )

        total_stock_units = sum(item.current_stock for item in annotated_items) or Decimal("0.00")
        low_stock_count = sum(
            1
            for item in annotated_items
            if item.reorder_threshold is not None and item.current_stock <= item.reorder_threshold
        )

        # 2. Expiry Counts
        perishable_txns = StockTransaction.objects.filter(
            organization=user_org, inventory_item__is_perishable=True, expiry_date__isnull=False
        )
        expiring_soon_count = perishable_txns.filter(
            expiry_date__gte=today, expiry_date__lte=seven_days
        ).count()
        expired_count = perishable_txns.filter(expiry_date__lt=today).count()

        # 3. Pending requests
        pending_requests_count = DistributionRequest.objects.filter(
            organization=user_org, status=DistributionRequest.Status.PENDING
        ).count()

        # 4. Activity this month
        month_donations = Donation.objects.filter(
            organization=user_org, date_received__year=today.year, date_received__month=today.month
        )
        donations_this_month_count = month_donations.count()
        items_donated_this_month = StockTransaction.objects.filter(
            organization=user_org,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            donation__date_received__year=today.year,
            donation__date_received__month=today.month,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")

        month_distributions = DistributionRequest.objects.filter(
            organization=user_org,
            status=DistributionRequest.Status.FULFILLED,
            reviewed_at__year=today.year,
            reviewed_at__month=today.month,
        )
        distributions_this_month_count = month_distributions.count()
        items_distributed_this_month = StockTransaction.objects.filter(
            organization=user_org,
            transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
            created_at__year=today.year,
            created_at__month=today.month,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")

        metrics_data = {
            "organization_name": user_org.name,
            "today": today,
            "total_distinct_items": total_distinct_items,
            "total_stock_units": total_stock_units,
            "low_stock_count": low_stock_count,
            "expiring_soon_count": expiring_soon_count,
            "expired_count": expired_count,
            "pending_requests_count": pending_requests_count,
            "donations_this_month_count": donations_this_month_count,
            "items_donated_this_month": items_donated_this_month,
            "distributions_this_month_count": distributions_this_month_count,
            "items_distributed_this_month": items_distributed_this_month,
        }

        serializer = DashboardMetricsSerializer(metrics_data)
        return Response(serializer.data)
