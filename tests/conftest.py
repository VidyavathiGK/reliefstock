from decimal import Decimal

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import User
from inventory.models import (
    Category,
    InventoryItem,
)
from organizations.models import Organization


@pytest.fixture
def org_a(db):
    return Organization.objects.create(
        name="Metro Hope Food Bank",
        org_type=Organization.OrgType.FOOD_BANK,
        contact_email="contact@metrohope.test",
        contact_phone="555-0100",
        address="100 Hope Way",
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name="Riverside Emergency Shelter",
        org_type=Organization.OrgType.SHELTER,
        contact_email="shelter@riverside.test",
        contact_phone="555-0200",
        address="200 River Road",
    )


@pytest.fixture
def admin_user(db, org_a):
    user = User.objects.create_user(
        username="admin_susan",
        email="admin@metrohope.test",
        password="TestPassword123!",
        role=User.Role.ADMIN,
        organization=org_a,
    )
    Token.objects.create(user=user)
    return user


@pytest.fixture
def staff_user(db, org_a):
    user = User.objects.create_user(
        username="staff_marcus",
        email="staff@metrohope.test",
        password="TestPassword123!",
        role=User.Role.STAFF,
        organization=org_a,
    )
    Token.objects.create(user=user)
    return user


@pytest.fixture
def volunteer_user(db, org_a):
    user = User.objects.create_user(
        username="vol_taylor",
        email="volunteer@metrohope.test",
        password="TestPassword123!",
        role=User.Role.VOLUNTEER,
        organization=org_a,
    )
    Token.objects.create(user=user)
    return user


@pytest.fixture
def donor_user(db):
    user = User.objects.create_user(
        username="donor_charlie",
        email="charlie@donor.test",
        password="TestPassword123!",
        role=User.Role.DONOR,
    )
    Token.objects.create(user=user)
    return user


@pytest.fixture
def other_org_staff(db, org_b):
    user = User.objects.create_user(
        username="staff_dan_riverside",
        email="dan@riverside.test",
        password="TestPassword123!",
        role=User.Role.STAFF,
        organization=org_b,
    )
    Token.objects.create(user=user)
    return user


@pytest.fixture
def category(db):
    return Category.objects.create(
        name="Canned & Dry Goods", description="Non-perishable essentials"
    )


@pytest.fixture
def rice_item(db, org_a, category):
    return InventoryItem.objects.create(
        name="White Rice (5kg)",
        category=category,
        organization=org_a,
        unit_of_measure="bags",
        reorder_threshold=Decimal("20.00"),
        is_perishable=False,
    )


@pytest.fixture
def milk_item(db, org_a, category):
    return InventoryItem.objects.create(
        name="Fresh Whole Milk",
        category=category,
        organization=org_a,
        unit_of_measure="cartons",
        reorder_threshold=Decimal("15.00"),
        is_perishable=True,
    )


@pytest.fixture
def api_client():
    return APIClient()
