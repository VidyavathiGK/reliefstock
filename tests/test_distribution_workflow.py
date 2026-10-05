from decimal import Decimal

import pytest
from django.utils import timezone

from inventory.models import (
    DistributionRequest,
    DistributionRequestItem,
    Donation,
    StockTransaction,
)


@pytest.mark.django_db
class TestDistributionLifecycle:
    """Tests the Request -> Approve -> Fulfill lifecycle."""

    @pytest.fixture(autouse=True)
    def stock_setup(self, org_a, staff_user, rice_item, milk_item):
        donation = Donation.objects.create(
            organization=org_a,
            donor_name="Regional Food Drive",
            date_received=timezone.localdate(),
            recorded_by=staff_user,
        )
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("100.00"),
            donation=donation,
            recorded_by=staff_user,
        )
        StockTransaction.objects.create(
            inventory_item=milk_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("50.00"),
            donation=donation,
            recorded_by=staff_user,
        )

    def test_request_creation_starts_pending(self, org_a, volunteer_user, rice_item):
        req = DistributionRequest.objects.create(
            organization=org_a,
            recipient_name="Community Kitchen A",
            recipient_contact="555-9999",
            requested_by=volunteer_user,
            status=DistributionRequest.Status.PENDING,
        )
        item = DistributionRequestItem.objects.create(
            distribution_request=req,
            inventory_item=rice_item,
            quantity_requested=Decimal("20.00"),
            quantity_fulfilled=Decimal("0.00"),
        )

        assert req.status == DistributionRequest.Status.PENDING
        assert item.quantity_remaining == Decimal("20.00")
        assert item.is_fully_fulfilled is False

    def test_admin_approve_and_fulfill(
        self, org_a, admin_user, staff_user, volunteer_user, rice_item
    ):
        req = DistributionRequest.objects.create(
            organization=org_a,
            recipient_name="Shelter Resident 4B",
            requested_by=volunteer_user,
            status=DistributionRequest.Status.PENDING,
        )
        line_item = DistributionRequestItem.objects.create(
            distribution_request=req,
            inventory_item=rice_item,
            quantity_requested=Decimal("25.00"),
            quantity_fulfilled=Decimal("0.00"),
        )

        # 1. Admin Approves
        req.status = DistributionRequest.Status.APPROVED
        req.reviewed_by = admin_user
        req.reviewed_at = timezone.now()
        req.save()

        # 2. Staff Fulfills completely
        line_item.quantity_fulfilled = Decimal("25.00")
        line_item.save()

        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
            quantity=Decimal("25.00"),
            distribution_request=req,
            recorded_by=staff_user,
        )

        req.status = DistributionRequest.Status.FULFILLED
        req.save()

        # Verify stock deducted
        assert rice_item.get_current_stock() == Decimal("75.00")
        assert line_item.is_fully_fulfilled is True
        assert req.status == DistributionRequest.Status.FULFILLED

    def test_partial_fulfillment_keeps_status_approved(
        self, org_a, admin_user, staff_user, volunteer_user, rice_item
    ):
        req = DistributionRequest.objects.create(
            organization=org_a,
            recipient_name="Family of Five",
            requested_by=volunteer_user,
            status=DistributionRequest.Status.APPROVED,
            reviewed_by=admin_user,
            reviewed_at=timezone.now(),
        )
        line_item = DistributionRequestItem.objects.create(
            distribution_request=req,
            inventory_item=rice_item,
            quantity_requested=Decimal("40.00"),
            quantity_fulfilled=Decimal("0.00"),
        )

        # Fulfill only 15.00
        line_item.quantity_fulfilled = Decimal("15.00")
        line_item.save()

        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
            quantity=Decimal("15.00"),
            distribution_request=req,
            recorded_by=staff_user,
        )

        assert line_item.quantity_remaining == Decimal("25.00")
        assert line_item.is_fully_fulfilled is False
        assert req.status == DistributionRequest.Status.APPROVED
        assert rice_item.get_current_stock() == Decimal("85.00")
