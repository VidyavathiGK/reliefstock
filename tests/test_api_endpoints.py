from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token

from inventory.models import (
    DistributionRequest,
    Donation,
    StockTransaction,
)


@pytest.mark.django_db
class TestRestApiEndpoints:
    """Tests for Django REST Framework API endpoints."""

    def test_obtain_auth_token(self, api_client, staff_user):
        url = "/api/v1/auth/token/"
        response = api_client.post(
            url, {"username": staff_user.username, "password": "TestPassword123!"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert "token" in response.data

    def test_unauthenticated_requests_are_rejected(self, api_client):
        response = api_client.get("/api/v1/items/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_items_with_token(self, api_client, staff_user, rice_item):
        token = Token.objects.get(user=staff_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.get("/api/v1/items/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["results"] if "results" in response.data else response.data
        assert len(data) >= 1
        assert data[0]["name"] == "White Rice (5kg)"
        assert "current_stock" in data[0]

    def test_multi_tenant_isolation_in_api(
        self, api_client, staff_user, other_org_staff, rice_item
    ):
        # Rice item belongs to Org A (staff_user)
        token_b = Token.objects.get(user=other_org_staff)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token_b.key}")

        # Org B staff should not see Rice item
        response = api_client.get("/api/v1/items/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["results"] if "results" in response.data else response.data
        item_names = [it["name"] for it in data]
        assert "White Rice (5kg)" not in item_names

    def test_record_donation_via_api_creates_ledger_entries(
        self, api_client, staff_user, rice_item
    ):
        token = Token.objects.get(user=staff_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        payload = {
            "donor_name": "Corporate Sponsor Corp",
            "donor_contact": "sponsor@corp.test",
            "date_received": str(timezone.localdate()),
            "notes": "Pallet of rice",
            "items": [
                {"inventory_item": rice_item.id, "quantity": "100.00", "note": "Standard packaging"}
            ],
        }

        response = api_client.post("/api/v1/donations/", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["donor_name"] == "Corporate Sponsor Corp"

        # Verify atomic stock update
        assert rice_item.get_current_stock() == Decimal("100.00")

    def test_distribution_request_review_and_fulfillment_api(
        self, api_client, admin_user, staff_user, volunteer_user, rice_item
    ):
        # 1. First add stock
        donation = Donation.objects.create(
            organization=rice_item.organization,
            donor_name="Donor",
            date_received=timezone.localdate(),
            recorded_by=staff_user,
        )
        StockTransaction.objects.create(
            inventory_item=rice_item,
            organization=rice_item.organization,
            transaction_type=StockTransaction.TransactionType.DONATION_IN,
            quantity=Decimal("50.00"),
            donation=donation,
            recorded_by=staff_user,
        )

        # 2. Volunteer creates distribution request via API
        vol_token = Token.objects.get(user=volunteer_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {vol_token.key}")

        create_payload = {
            "recipient_name": "Emergency Shelter Client",
            "recipient_contact": "555-4321",
            "notes": "Urgent food assistance",
            "items": [{"inventory_item": rice_item.id, "quantity_requested": "20.00"}],
        }
        res_create = api_client.post(
            "/api/v1/distribution-requests/", create_payload, format="json"
        )
        assert res_create.status_code == status.HTTP_201_CREATED
        req_id = res_create.data["id"]
        assert res_create.data["status"] == "PENDING"

        # Line item ID
        req_obj = DistributionRequest.objects.get(pk=req_id)
        line_item_id = req_obj.items.first().id

        # 3. Staff tries to approve (should be blocked - Admin only)
        staff_token = Token.objects.get(user=staff_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token.key}")
        res_staff_review = api_client.post(
            f"/api/v1/distribution-requests/{req_id}/review/", {"action": "APPROVE"}
        )
        assert res_staff_review.status_code == status.HTTP_403_FORBIDDEN

        # 4. Admin approves
        admin_token = Token.objects.get(user=admin_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")
        res_admin_review = api_client.post(
            f"/api/v1/distribution-requests/{req_id}/review/",
            {"action": "APPROVE", "notes": "Approved by lead admin"},
        )
        assert res_admin_review.status_code == status.HTTP_200_OK
        assert res_admin_review.data["status"] == "APPROVED"

        # 5. Staff fulfills the approved request
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token.key}")
        fulfill_payload = {
            "notes": "All 20 bags dispatched",
            "dispatches": [{"item_id": line_item_id, "quantity_to_fulfill": "20.00"}],
        }
        res_fulfill = api_client.post(
            f"/api/v1/distribution-requests/{req_id}/fulfill/", fulfill_payload, format="json"
        )
        assert res_fulfill.status_code == status.HTTP_200_OK
        assert res_fulfill.data["status"] == "FULFILLED"
        assert res_fulfill.data["is_fully_fulfilled"] is True

        # Verify stock deducted
        assert rice_item.get_current_stock() == Decimal("30.00")

    def test_dashboard_api_endpoint(self, api_client, staff_user, rice_item):
        token = Token.objects.get(user=staff_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = api_client.get("/api/v1/dashboard/")
        assert response.status_code == status.HTTP_200_OK
        assert "total_distinct_items" in response.data
        assert "total_stock_units" in response.data
        assert "low_stock_count" in response.data
        assert "pending_requests_count" in response.data

    def test_donor_access_isolation(self, api_client, donor_user, org_a, staff_user, rice_item):
        # Create a donation linked to this donor
        Donation.objects.create(
            organization=org_a,
            donor_name="Charlie Donor",
            donor_user=donor_user,
            date_received=timezone.localdate(),
            recorded_by=staff_user,
        )

        donor_token = Token.objects.get(user=donor_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {donor_token.key}")

        # Donor can retrieve own donations
        res_donations = api_client.get("/api/v1/donations/")
        assert res_donations.status_code == status.HTTP_200_OK
        data = (
            res_donations.data["results"] if "results" in res_donations.data else res_donations.data
        )
        assert len(data) == 1
        assert data[0]["donor_name"] == "Charlie Donor"

        # Donor cannot view internal inventory items
        res_items = api_client.get("/api/v1/items/")
        assert res_items.status_code == status.HTTP_403_FORBIDDEN

        # Donor cannot access staff dashboard
        res_dash = api_client.get("/api/v1/dashboard/")
        assert res_dash.status_code == status.HTTP_403_FORBIDDEN
