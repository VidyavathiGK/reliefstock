from django.test import TestCase
from django.db import IntegrityError
from organizations.models import Organization
from inventory.models import Category, InventoryItem


class InventoryModelTests(TestCase):
    """
    Test suite for Category and InventoryItem models.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            name="Community Pantry West",
            org_type=Organization.OrgType.FOOD_BANK,
            address="789 Market Ave",
            contact_email="west@pantry.org",
            contact_phone="555-0188"
        )
        self.category = Category.objects.create(
            name="Grains & Pasta",
            description="Rice, oats, pasta, and whole grains"
        )

    def test_category_creation(self):
        self.assertEqual(str(self.category), "Grains & Pasta")

    def test_inventory_item_creation(self):
        item = InventoryItem.objects.create(
            name="Rolled Oats 1kg",
            category=self.category,
            unit_of_measure="bags",
            is_perishable=False,
            organization=self.org
        )
        self.assertEqual(item.name, "Rolled Oats 1kg")
        self.assertEqual(item.unit_of_measure, "bags")
        self.assertFalse(item.is_perishable)
        self.assertEqual(item.organization, self.org)
        self.assertEqual(str(item), "Rolled Oats 1kg (Community Pantry West) - [bags]")

    def test_unique_item_per_organization_constraint(self):
        """Ensure duplicate items with identical names in the same organization are prevented."""
        InventoryItem.objects.create(
            name="Standard Blankets",
            category=self.category,
            unit_of_measure="pieces",
            is_perishable=False,
            organization=self.org
        )
        with self.assertRaises(IntegrityError):
            InventoryItem.objects.create(
                name="Standard Blankets",
                category=self.category,
                unit_of_measure="pieces",
                is_perishable=False,
                organization=self.org
            )
