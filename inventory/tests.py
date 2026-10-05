from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from inventory.models import (
    Category,
    DistributionRequest,
    DistributionRequestItem,
    Donation,
    InventoryItem,
    StockTransaction,
)
from organizations.models import Organization


class InventoryPhase2Tests(TestCase):
    """
    Comprehensive test suite for Phase 2:
    - StockTransaction and Donation models
    - Real-time stock calculation (ledger aggregation)
    - Data integrity checks (clean validations)
    - Role-Based Access Control (Admin, Staff, Volunteer, Donor)
    - Multi-item donation intake view
    - Manual stock adjustment view
    """

    def setUp(self):
        self.client = Client()

        # Organizations
        self.org1 = Organization.objects.create(
            name="Downtown Relief Center",
            org_type=Organization.OrgType.FOOD_BANK,
            address="100 Main St",
            contact_email="contact@downtownrelief.org",
            contact_phone="555-0100",
        )
        self.org2 = Organization.objects.create(
            name="Eastside Shelter",
            org_type=Organization.OrgType.SHELTER,
            address="200 East St",
            contact_email="contact@eastsideshelter.org",
            contact_phone="555-0200",
        )

        # Users with distinct roles
        self.staff_user = User.objects.create_user(
            username="staff_member",
            password="TestPassword123!",
            role=User.Role.STAFF,
            organization=self.org1,
        )
        self.admin_user = User.objects.create_user(
            username="admin_member",
            password="TestPassword123!",
            role=User.Role.ADMIN,
            organization=self.org1,
        )
        self.volunteer_user = User.objects.create_user(
            username="volunteer_member",
            password="TestPassword123!",
            role=User.Role.VOLUNTEER,
            organization=self.org1,
        )
        self.donor_user = User.objects.create_user(
            username="donor_member",
            password="TestPassword123!",
            role=User.Role.DONOR,
            organization=self.org1,
        )

        # Catalog
        self.category = Category.objects.create(
            name="Canned Goods", description="Canned soups and veggies"
        )
        self.item_beans = InventoryItem.objects.create(
            name="Canned Black Beans 400g",
            category=self.category,
            unit_of_measure="cans",
            is_perishable=False,
            organization=self.org1,
        )
        self.item_milk = InventoryItem.objects.create(
            name="Whole Milk 1L",
            category=self.category,
            unit_of_measure="liters",
            is_perishable=True,
            organization=self.org1,
        )

    # -------------------------------------------------------------
    # 1. Stock Calculation & Ledger Tests
    # -------------------------------------------------------------
    def test_stock_calculation_flow(self):
        """Verify dynamic calculation: 0 -> +Donation -> +Manual In -> -Manual Out."""
        # 1. Initial stock is 0
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("0.00"))

        # 2. Donation adds 50 cans
        donation = Donation.objects.create(
            donor_name="Local Grocery", organization=self.org1, recorded_by=self.staff_user
        )
        StockTransaction.objects.create(
            inventory_item=self.item_beans,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("50.00"),
            organization=self.org1,
            recorded_by=self.staff_user,
            donation=donation,
        )
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("50.00"))

        # 3. Manual adjustment in adds 10 cans
        StockTransaction.objects.create(
            inventory_item=self.item_beans,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
            quantity=Decimal("10.00"),
            organization=self.org1,
            recorded_by=self.staff_user,
            note="Found extra carton in storage",
        )
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("60.00"))

        # 4. Manual adjustment out deducts 5 cans
        StockTransaction.objects.create(
            inventory_item=self.item_beans,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
            quantity=Decimal("5.00"),
            organization=self.org1,
            recorded_by=self.staff_user,
            note="Dented cans discarded",
        )
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("55.00"))

    # -------------------------------------------------------------
    # 2. Data Integrity & Validation Checks
    # -------------------------------------------------------------
    def test_organization_mismatch_validation(self):
        """A StockTransaction must match the item's organization."""
        txn = StockTransaction(
            inventory_item=self.item_beans,  # org1
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("10.00"),
            organization=self.org2,  # mismatched org2
            recorded_by=self.staff_user,
        )
        with self.assertRaises(ValidationError) as ctx:
            txn.full_clean()
        self.assertIn("organization", ctx.exception.message_dict)

    def test_manual_adjustment_requires_note(self):
        """Manual adjustments must include an explanatory note."""
        txn = StockTransaction(
            inventory_item=self.item_beans,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
            quantity=Decimal("10.00"),
            organization=self.org1,
            recorded_by=self.staff_user,
            note="",  # Empty note
        )
        with self.assertRaises(ValidationError) as ctx:
            txn.full_clean()
        self.assertIn("note", ctx.exception.message_dict)

    def test_expiry_date_forbidden_on_non_perishables(self):
        """Expiry date is rejected on items where is_perishable=False."""
        from django.utils import timezone

        txn = StockTransaction(
            inventory_item=self.item_beans,  # is_perishable=False
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("10.00"),
            organization=self.org1,
            recorded_by=self.staff_user,
            expiry_date=timezone.now().date(),
        )
        with self.assertRaises(ValidationError) as ctx:
            txn.full_clean()
        self.assertIn("expiry_date", ctx.exception.message_dict)

    def test_cannot_deduct_more_than_available_stock(self):
        """Cannot execute a manual reduction greater than current stock."""
        # Current stock is 0
        txn = StockTransaction(
            inventory_item=self.item_beans,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
            quantity=Decimal("10.00"),
            organization=self.org1,
            recorded_by=self.staff_user,
            note="Trying to deduct non-existent stock",
        )
        with self.assertRaises(ValidationError) as ctx:
            txn.full_clean()
        self.assertIn("quantity", ctx.exception.message_dict)

    # -------------------------------------------------------------
    # 3. Multi-Item Donation View Tests
    # -------------------------------------------------------------
    def test_record_donation_with_multiple_items_as_staff(self):
        """Staff can log a donation with 2+ items in a single form submission."""
        self.client.login(username="staff_member", password="TestPassword123!")

        post_data = {
            "donor_name": "Baker Community Market",
            "donor_contact": "baker@market.com",
            "date_received": "2026-10-02",
            "notes": "Weekly community food surplus drop-off",
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            # Item 1: Beans (non-perishable)
            "form-0-inventory_item": str(self.item_beans.pk),
            "form-0-quantity": "40.00",
            "form-0-note": "Case A",
            "form-0-expiry_date": "",
            # Item 2: Milk (perishable)
            "form-1-inventory_item": str(self.item_milk.pk),
            "form-1-quantity": "25.00",
            "form-1-note": "Cold storage",
            "form-1-expiry_date": "2026-10-15",
        }

        response = self.client.post(reverse("inventory:record_donation"), post_data)
        self.assertEqual(response.status_code, 302)  # Redirects to inventory list

        # Verify donation created
        donation = Donation.objects.get(donor_name="Baker Community Market")
        self.assertEqual(donation.stock_transactions.count(), 2)

        # Verify stock updated
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("40.00"))
        self.assertEqual(self.item_milk.get_current_stock(), Decimal("25.00"))

        # Verify inventory list view displays updated stock
        list_response = self.client.get(reverse("inventory:inventory_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "40.00")
        self.assertContains(list_response, "25.00")

    # -------------------------------------------------------------
    # 4. Manual Stock Adjustment View & Item Detail History Tests
    # -------------------------------------------------------------
    def test_manual_stock_adjustment_and_chronological_history(self):
        """Staff can manually adjust stock and see it on the item detail page."""
        self.client.login(username="staff_member", password="TestPassword123!")

        # 1. First add some stock via manual addition
        add_data = {
            "transaction_type": StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
            "quantity": "100.00",
            "note": "Initial count verification",
            "expiry_date": "",
        }
        res = self.client.post(
            reverse("inventory:manual_adjustment", args=[self.item_beans.pk]), add_data
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("100.00"))

        # 2. Deduct 15 cans via manual reduction
        sub_data = {
            "transaction_type": StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
            "quantity": "15.00",
            "note": "Damaged boxes in transit",
            "expiry_date": "",
        }
        res = self.client.post(
            reverse("inventory:manual_adjustment", args=[self.item_beans.pk]), sub_data
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("85.00"))

        # 3. Item detail view shows chronological transaction log
        detail_res = self.client.get(
            reverse("inventory:inventory_detail", args=[self.item_beans.pk])
        )
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "85.00 cans")
        self.assertContains(detail_res, "+100.00")
        self.assertContains(detail_res, "-15.00")
        self.assertContains(detail_res, "Initial count verification")
        self.assertContains(detail_res, "Damaged boxes in transit")

    # -------------------------------------------------------------
    # 5. Role-Based Access Control (RBAC) Tests
    # -------------------------------------------------------------
    def test_volunteer_can_record_donation_but_blocked_from_inventory(self):
        """Volunteer CAN record a donation, but is blocked from inventory list & adjustment."""
        self.client.login(username="volunteer_member", password="TestPassword123!")

        # 1. Volunteer accesses record donation page: Allowed (200)
        get_res = self.client.get(reverse("inventory:record_donation"))
        self.assertEqual(get_res.status_code, 200)

        # 2. Volunteer records donation: Allowed (302 redirect back to donation form)
        donation_data = {
            "donor_name": "Volunteer Friend",
            "donor_contact": "",
            "date_received": "2026-10-02",
            "notes": "",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-inventory_item": str(self.item_beans.pk),
            "form-0-quantity": "12.00",
            "form-0-note": "",
            "form-0-expiry_date": "",
        }
        post_res = self.client.post(reverse("inventory:record_donation"), donation_data)
        self.assertEqual(post_res.status_code, 302)
        self.assertEqual(self.item_beans.get_current_stock(), Decimal("12.00"))

        # 3. Volunteer tries to access inventory list: Denied (Redirected to home)
        list_res = self.client.get(reverse("inventory:inventory_list"))
        self.assertEqual(list_res.status_code, 302)
        self.assertIn(reverse("home"), list_res.url)

        # 4. Volunteer tries to access manual adjustment: Denied (Redirected to home)
        adj_res = self.client.get(reverse("inventory:manual_adjustment", args=[self.item_beans.pk]))
        self.assertEqual(adj_res.status_code, 302)
        self.assertIn(reverse("home"), adj_res.url)

    def test_donor_blocked_from_all_staff_views(self):
        """Donor role is forbidden from inventory list, adjustment, and donation entry."""
        self.client.login(username="donor_member", password="TestPassword123!")

        for url in [
            reverse("inventory:inventory_list"),
            reverse("inventory:inventory_detail", args=[self.item_beans.pk]),
            reverse("inventory:manual_adjustment", args=[self.item_beans.pk]),
            reverse("inventory:record_donation"),
        ]:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302, f"Donor was not blocked from {url}")
            self.assertIn(reverse("home"), res.url)


class InventoryPhase3Tests(TestCase):
    """
    Comprehensive test suite for Phase 3:
    - DistributionRequest and DistributionRequestItem models
    - Multi-item distribution request creation by Volunteer and Staff
    - Administrative review flow (Approve / Reject)
    - Fulfillment flow with atomic stock deduction (DISTRIBUTION_OUT)
    - Prevention of over-fulfillment beyond available stock
    - Partial fulfillment mechanics (retaining APPROVED status with outstanding balances)
    - Perishable expiry tracking (Expiring Soon within 7 days vs Expired)
    - Low-stock alerts against reorder_threshold
    - Role-Based Access Control (Admin, Staff, Volunteer, Donor)
    """

    def setUp(self):
        self.client = Client()

        # Organizations
        self.org1 = Organization.objects.create(
            name="Downtown Relief Center",
            org_type=Organization.OrgType.FOOD_BANK,
            address="100 Main St",
            contact_email="contact@downtownrelief.org",
            contact_phone="555-0100",
        )
        self.org2 = Organization.objects.create(
            name="Eastside Shelter",
            org_type=Organization.OrgType.SHELTER,
            address="200 East St",
            contact_email="contact@eastsideshelter.org",
            contact_phone="555-0200",
        )

        # Users
        self.admin_user = User.objects.create_user(
            username="phase3_admin",
            password="TestPassword123!",
            role=User.Role.ADMIN,
            organization=self.org1,
        )
        self.staff_user = User.objects.create_user(
            username="phase3_staff",
            password="TestPassword123!",
            role=User.Role.STAFF,
            organization=self.org1,
        )
        self.volunteer_user = User.objects.create_user(
            username="phase3_volunteer",
            password="TestPassword123!",
            role=User.Role.VOLUNTEER,
            organization=self.org1,
        )
        self.donor_user = User.objects.create_user(
            username="phase3_donor",
            password="TestPassword123!",
            role=User.Role.DONOR,
            organization=self.org1,
        )

        # Catalog
        self.category = Category.objects.create(
            name="Pantry Staples", description="Basic dry and canned goods"
        )
        self.rice = InventoryItem.objects.create(
            name="White Rice 1kg",
            category=self.category,
            unit_of_measure="bags",
            is_perishable=False,
            organization=self.org1,
            reorder_threshold=Decimal("20.00"),
        )
        self.soup = InventoryItem.objects.create(
            name="Tomato Soup 400g",
            category=self.category,
            unit_of_measure="cans",
            is_perishable=False,
            organization=self.org1,
            reorder_threshold=Decimal("15.00"),
        )
        self.yogurt = InventoryItem.objects.create(
            name="Greek Yogurt 500g",
            category=self.category,
            unit_of_measure="tubs",
            is_perishable=True,
            organization=self.org1,
        )

        # Seed initial stock via donation
        StockTransaction.objects.create(
            inventory_item=self.rice,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("50.00"),
            recorded_by=self.staff_user,
            organization=self.org1,
            note="Initial rice stock",
        )
        StockTransaction.objects.create(
            inventory_item=self.soup,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("10.00"),
            recorded_by=self.staff_user,
            organization=self.org1,
            note="Initial soup stock",
        )

    # -------------------------------------------------------------
    # 1. Distribution Request Submission Tests
    # -------------------------------------------------------------
    def test_volunteer_can_create_distribution_request_with_multiple_items(self):
        """A VOLUNTEER can record a distribution request with 2+ items in one form."""
        self.client.login(username="phase3_volunteer", password="TestPassword123!")

        post_data = {
            "recipient_name": "Family of Four (Shelter Room 102)",
            "recipient_contact": "555-9876",
            "notes": "Urgent food relief for newly arrived family",
            "form-TOTAL_FORMS": "5",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-inventory_item": str(self.rice.pk),
            "form-0-quantity_requested": "10.00",
            "form-1-inventory_item": str(self.soup.pk),
            "form-1-quantity_requested": "6.00",
        }

        res = self.client.post(reverse("inventory:distribution_request_create"), post_data)
        self.assertEqual(res.status_code, 302)

        # Verify database record
        req = DistributionRequest.objects.get(recipient_name="Family of Four (Shelter Room 102)")
        self.assertEqual(req.status, DistributionRequest.Status.PENDING)
        self.assertEqual(req.requested_by, self.volunteer_user)
        self.assertEqual(req.organization, self.org1)
        self.assertEqual(req.items.count(), 2)

        # Check line items
        rice_line = req.items.get(inventory_item=self.rice)
        self.assertEqual(rice_line.quantity_requested, Decimal("10.00"))
        self.assertEqual(rice_line.quantity_fulfilled, Decimal("0.00"))
        self.assertEqual(rice_line.quantity_remaining, Decimal("10.00"))

        soup_line = req.items.get(inventory_item=self.soup)
        self.assertEqual(soup_line.quantity_requested, Decimal("6.00"))

    # -------------------------------------------------------------
    # 2. Administrative Review (Approve / Reject) Tests
    # -------------------------------------------------------------
    def test_admin_review_approve_request(self):
        """ADMIN can review and approve a pending request."""
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="John Doe",
            status=DistributionRequest.Status.PENDING,
        )
        DistributionRequestItem.objects.create(
            distribution_request=req, inventory_item=self.rice, quantity_requested=Decimal("5.00")
        )

        self.client.login(username="phase3_admin", password="TestPassword123!")
        post_data = {"action": "APPROVE", "review_notes": "All good to dispatch."}
        res = self.client.post(
            reverse("inventory:distribution_request_review", args=[req.pk]), post_data
        )
        self.assertEqual(res.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, DistributionRequest.Status.APPROVED)
        self.assertEqual(req.reviewed_by, self.admin_user)
        self.assertIsNotNone(req.reviewed_at)
        self.assertIn("All good to dispatch", req.notes)

    def test_admin_review_reject_request(self):
        """ADMIN can reject a pending request with an explanatory note."""
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Jane Doe",
            status=DistributionRequest.Status.PENDING,
        )
        DistributionRequestItem.objects.create(
            distribution_request=req, inventory_item=self.rice, quantity_requested=Decimal("5.00")
        )

        self.client.login(username="phase3_admin", password="TestPassword123!")
        post_data = {
            "action": "REJECT",
            "review_notes": "Recipient already received quota this week.",
        }
        res = self.client.post(
            reverse("inventory:distribution_request_review", args=[req.pk]), post_data
        )
        self.assertEqual(res.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, DistributionRequest.Status.REJECTED)
        self.assertEqual(req.reviewed_by, self.admin_user)
        self.assertIn("Recipient already received quota", req.notes)

    # -------------------------------------------------------------
    # 3. Fulfillment & Stock Deduction Tests
    # -------------------------------------------------------------
    def test_staff_fulfill_request_completely_deducts_stock(self):
        """STAFF fulfills an approved request completely, creating DISTRIBUTION_OUT ledger records."""
        # Initial stock: Rice = 50.00
        self.assertEqual(self.rice.get_current_stock(), Decimal("50.00"))

        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
            recipient_name="Client Alpha",
            status=DistributionRequest.Status.APPROVED,
        )
        line = DistributionRequestItem.objects.create(
            distribution_request=req, inventory_item=self.rice, quantity_requested=Decimal("15.00")
        )

        self.client.login(username="phase3_staff", password="TestPassword123!")
        post_data = {
            f"fulfill_item_{line.id}": "15.00",
            "fulfillment_note": "Dispatched via pickup van",
        }
        res = self.client.post(
            reverse("inventory:distribution_request_fulfill", args=[req.pk]), post_data
        )
        self.assertEqual(res.status_code, 302)

        req.refresh_from_db()
        line.refresh_from_db()

        # Request marked fulfilled
        self.assertEqual(req.status, DistributionRequest.Status.FULFILLED)
        self.assertEqual(line.quantity_fulfilled, Decimal("15.00"))
        self.assertTrue(line.is_fully_fulfilled)

        # Stock deducted: 50.00 - 15.00 = 35.00
        self.assertEqual(self.rice.get_current_stock(), Decimal("35.00"))

        # Verify StockTransaction record
        txn = StockTransaction.objects.get(distribution_request=req)
        self.assertEqual(txn.transaction_type, StockTransaction.TransactionType.DISTRIBUTION_OUT)
        self.assertEqual(txn.quantity, Decimal("15.00"))
        self.assertEqual(txn.recorded_by, self.staff_user)

    def test_over_fulfillment_is_blocked_with_error(self):
        """Attempting to fulfill more than current available stock is blocked with clear error."""
        # Soup has 10.00 in stock
        self.assertEqual(self.soup.get_current_stock(), Decimal("10.00"))

        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Client Beta",
            status=DistributionRequest.Status.APPROVED,
        )
        line = DistributionRequestItem.objects.create(
            distribution_request=req, inventory_item=self.soup, quantity_requested=Decimal("20.00")
        )

        self.client.login(username="phase3_staff", password="TestPassword123!")
        # Attempt to dispatch 15 cans (only 10 on hand)
        post_data = {
            f"fulfill_item_{line.id}": "15.00",
            "fulfillment_note": "Trying to over-dispatch",
        }
        res = self.client.post(
            reverse("inventory:distribution_request_fulfill", args=[req.pk]), post_data
        )
        self.assertEqual(res.status_code, 200)  # Form redisplays with error
        self.assertContains(
            res,
            "Insufficient stock for &#x27;Tomato Soup 400g&#x27;. Available: 10.00 cans, attempted to dispatch: 15.00.",
        )

        # Ensure no stock movement occurred
        self.assertEqual(self.soup.get_current_stock(), Decimal("10.00"))
        req.refresh_from_db()
        self.assertEqual(req.status, DistributionRequest.Status.APPROVED)

    def test_partial_fulfillment_flow(self):
        """Staff can partially fulfill what's available; status remains APPROVED with outstanding note."""
        # Soup stock is 10.00; Request is for 20.00
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Client Gamma",
            status=DistributionRequest.Status.APPROVED,
        )
        line = DistributionRequestItem.objects.create(
            distribution_request=req, inventory_item=self.soup, quantity_requested=Decimal("20.00")
        )

        self.client.login(username="phase3_staff", password="TestPassword123!")
        # Fulfill only what is available: 10.00
        post_data = {
            f"fulfill_item_{line.id}": "10.00",
            "fulfillment_note": "Dispatched initial 10 cans, awaiting restock",
        }
        res = self.client.post(
            reverse("inventory:distribution_request_fulfill", args=[req.pk]), post_data
        )
        self.assertEqual(res.status_code, 302)

        req.refresh_from_db()
        line.refresh_from_db()

        # Status must remain APPROVED for remaining items
        self.assertEqual(req.status, DistributionRequest.Status.APPROVED)
        self.assertEqual(line.quantity_fulfilled, Decimal("10.00"))
        self.assertEqual(line.quantity_remaining, Decimal("10.00"))
        self.assertFalse(line.is_fully_fulfilled)

        # Stock reduced to 0
        self.assertEqual(self.soup.get_current_stock(), Decimal("0.00"))

        # Notes contain outstanding balance summary
        self.assertIn("Tomato Soup 400g: 10.00 cans remaining", req.notes)

    # -------------------------------------------------------------
    # 4. Monitoring & Alert Views Tests
    # -------------------------------------------------------------
    def test_expiring_soon_and_expired_filters(self):
        """Tests that 'Expiring Soon' shows items expiring within 7 days and 'Expired' shows overdue items."""
        today = timezone.localdate()

        # Batch 1: Expiring in 3 days (Expiring soon)
        StockTransaction.objects.create(
            inventory_item=self.yogurt,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("12.00"),
            expiry_date=today + timedelta(days=3),
            recorded_by=self.staff_user,
            organization=self.org1,
            note="Expiring in 3 days batch",
        )
        # Batch 2: Expired 2 days ago
        StockTransaction.objects.create(
            inventory_item=self.yogurt,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("8.00"),
            expiry_date=today - timedelta(days=2),
            recorded_by=self.staff_user,
            organization=self.org1,
            note="Already expired batch",
        )
        # Batch 3: Expiring in 30 days (Not expiring soon)
        StockTransaction.objects.create(
            inventory_item=self.yogurt,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("25.00"),
            expiry_date=today + timedelta(days=30),
            recorded_by=self.staff_user,
            organization=self.org1,
            note="Far future batch",
        )

        self.client.login(username="phase3_staff", password="TestPassword123!")

        # 1. Expiring soon view (default)
        res_soon = self.client.get(reverse("inventory:expiring_stock_list"))
        self.assertEqual(res_soon.status_code, 200)
        self.assertContains(res_soon, "Expiring in 3 days batch")
        self.assertNotContains(res_soon, "Already expired batch")
        self.assertNotContains(res_soon, "Far future batch")

        # 2. Expired view
        res_expired = self.client.get(reverse("inventory:expiring_stock_list") + "?filter=expired")
        self.assertEqual(res_expired.status_code, 200)
        self.assertContains(res_expired, "Already expired batch")
        self.assertNotContains(res_expired, "Expiring in 3 days batch")
        self.assertNotContains(res_expired, "Far future batch")

    def test_low_stock_list_view(self):
        """Items with current_stock <= reorder_threshold appear in the low-stock alert list."""
        # Rice: stock = 50.00, reorder_threshold = 20.00 -> Healthy (Not in low stock)
        # Soup: stock = 10.00, reorder_threshold = 15.00 -> Low stock (Deficit: 5.00)
        self.client.login(username="phase3_staff", password="TestPassword123!")
        res = self.client.get(reverse("inventory:low_stock_list"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.soup.name)
        self.assertNotContains(res, self.rice.name)

    # -------------------------------------------------------------
    # 5. Role-Based Access Control (RBAC) Tests
    # -------------------------------------------------------------
    def test_volunteer_permissions_boundary(self):
        """Volunteer can create requests, but cannot review, fulfill, or view stock alert lists."""
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Volunteer Bound Test",
            status=DistributionRequest.Status.APPROVED,
        )
        self.client.login(username="phase3_volunteer", password="TestPassword123!")

        # Volunteer CAN access create request view
        res_create = self.client.get(reverse("inventory:distribution_request_create"))
        self.assertEqual(res_create.status_code, 200)

        # Volunteer CAN access distribution request list
        res_list = self.client.get(reverse("inventory:distribution_request_list"))
        self.assertEqual(res_list.status_code, 200)

        # Volunteer CANNOT review requests (Blocked / redirected)
        res_review = self.client.get(
            reverse("inventory:distribution_request_review", args=[req.pk])
        )
        self.assertEqual(res_review.status_code, 302)
        self.assertIn(reverse("home"), res_review.url)

        # Volunteer CANNOT fulfill requests (Blocked / redirected)
        res_fulfill = self.client.get(
            reverse("inventory:distribution_request_fulfill", args=[req.pk])
        )
        self.assertEqual(res_fulfill.status_code, 302)
        self.assertIn(reverse("home"), res_fulfill.url)

        # Volunteer CANNOT view low stock or expiring stock
        res_low = self.client.get(reverse("inventory:low_stock_list"))
        self.assertEqual(res_low.status_code, 302)
        res_exp = self.client.get(reverse("inventory:expiring_stock_list"))
        self.assertEqual(res_exp.status_code, 302)

    def test_staff_cannot_review_requests(self):
        """Staff can fulfill approved requests, but CANNOT review/approve/reject requests."""
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Staff Bound Test",
            status=DistributionRequest.Status.PENDING,
        )
        self.client.login(username="phase3_staff", password="TestPassword123!")

        # Staff blocked from review
        res_review = self.client.get(
            reverse("inventory:distribution_request_review", args=[req.pk])
        )
        self.assertEqual(res_review.status_code, 302)
        self.assertIn(reverse("home"), res_review.url)

    def test_admin_has_full_workflow_access(self):
        """Admin can access creation, review, fulfillment, and alert monitoring."""
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Admin Full Test",
            status=DistributionRequest.Status.PENDING,
        )
        self.client.login(username="phase3_admin", password="TestPassword123!")

        # Admin CAN review
        res_review = self.client.get(
            reverse("inventory:distribution_request_review", args=[req.pk])
        )
        self.assertEqual(res_review.status_code, 200)

        # Admin CAN view low stock and expiring stock
        res_low = self.client.get(reverse("inventory:low_stock_list"))
        self.assertEqual(res_low.status_code, 200)
        res_exp = self.client.get(reverse("inventory:expiring_stock_list"))
        self.assertEqual(res_exp.status_code, 200)

    # -------------------------------------------------------------
    # 6. Model Data Integrity Validations
    # -------------------------------------------------------------
    def test_distribution_request_cross_organization_blocked(self):
        """Cannot link an inventory item from another organization to a distribution request."""
        # Item in org2
        org2_item = InventoryItem.objects.create(
            name="Org 2 Blankets",
            category=self.category,
            unit_of_measure="pieces",
            organization=self.org2,
        )
        req = DistributionRequest.objects.create(
            organization=self.org1,
            requested_by=self.volunteer_user,
            recipient_name="Org Mismatch Client",
        )
        line = DistributionRequestItem(
            distribution_request=req, inventory_item=org2_item, quantity_requested=Decimal("5.00")
        )
        with self.assertRaises(ValidationError):
            line.full_clean()
