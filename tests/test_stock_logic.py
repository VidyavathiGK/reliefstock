from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from inventory.models import Donation, StockTransaction


@pytest.mark.django_db
class TestStockCalculationsAndLedger:
    """Tests core inventory ledger and stock computation logic."""

    def test_initial_stock_is_zero(self, rice_item):
        assert rice_item.get_current_stock() == Decimal("0.00")

    def test_donation_intake_increases_stock(self, org_a, staff_user, rice_item):
        donation = Donation.objects.create(
            organization=org_a,
            donor_name="Local Community Market",
            date_received=timezone.localdate(),
            recorded_by=staff_user,
        )
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("50.00"),
            donation=donation,
            recorded_by=staff_user,
        )

        assert rice_item.get_current_stock() == Decimal("50.00")

    def test_manual_adjustment_increases_and_decreases_stock(self, org_a, staff_user, rice_item):
        # Adjustment IN
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
            quantity=Decimal("30.00"),
            recorded_by=staff_user,
            note="Found extra stock during audit",
        )
        assert rice_item.get_current_stock() == Decimal("30.00")

        # Adjustment OUT
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
            quantity=Decimal("10.00"),
            recorded_by=staff_user,
            note="Water damage write-off",
        )
        assert rice_item.get_current_stock() == Decimal("20.00")

    def test_low_stock_property(self, org_a, staff_user, rice_item):
        # Threshold is 20.00, current stock is 0.00 -> is_low_stock should be True
        assert rice_item.is_low_stock is True

        # Donate 25.00 -> stock becomes 25.00 > 20.00 -> is_low_stock should be False
        donation = Donation.objects.create(
            organization=org_a,
            donor_name="Generous Patron",
            date_received=timezone.localdate(),
            recorded_by=staff_user,
        )
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("25.00"),
            donation=donation,
            recorded_by=staff_user,
        )
        assert rice_item.get_current_stock() == Decimal("25.00")
        assert rice_item.is_low_stock is False

        # Adjustment OUT of 10.00 -> stock becomes 15.00 <= 20.00 -> is_low_stock should be True
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
            quantity=Decimal("10.00"),
            recorded_by=staff_user,
            note="Stock allocation",
        )
        assert rice_item.get_current_stock() == Decimal("15.00")
        assert rice_item.is_low_stock is True

    def test_perishable_expiry_tracking(self, org_a, staff_user, milk_item):
        today = timezone.localdate()

        # Batch 1: Expiring in 3 days (expiring soon)
        txn_soon = StockTransaction.objects.create(
            inventory_item=milk_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("10.00"),
            expiry_date=today + timedelta(days=3),
            recorded_by=staff_user,
        )

        # Batch 2: Expired 2 days ago
        txn_expired = StockTransaction.objects.create(
            inventory_item=milk_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("5.00"),
            expiry_date=today - timedelta(days=2),
            recorded_by=staff_user,
        )

        # Batch 3: Fresh, expiring in 30 days
        StockTransaction.objects.create(
            inventory_item=milk_item,
            organization=org_a,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("20.00"),
            expiry_date=today + timedelta(days=30),
            recorded_by=staff_user,
        )

        perishables = StockTransaction.objects.filter(
            organization=org_a, inventory_item__is_perishable=True
        )

        expiring_soon = perishables.filter(
            expiry_date__gte=today, expiry_date__lte=today + timedelta(days=7)
        )
        assert expiring_soon.count() == 1
        assert expiring_soon.first().id == txn_soon.id

        expired = perishables.filter(expiry_date__lt=today)
        assert expired.count() == 1
        assert expired.first().id == txn_expired.id
