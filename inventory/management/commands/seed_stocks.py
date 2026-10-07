"""
Management command to seed realistic, production-ready humanitarian relief
inventory stocks, categories, donations, and distribution requests.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
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


class Command(BaseCommand):
    help = "Populate database with rich, realistic NGO relief inventory stocks and ledger records."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding professional relief inventory stocks...")

        # 1. Target Organization: Org Alpha Food Bank (or fallback to first org)
        org = Organization.objects.filter(name__icontains="Alpha").first()
        if not org:
            org = Organization.objects.first()
        if not org:
            org = Organization.objects.create(
                name="Metro Relief Food Bank & Shelter",
                org_type=Organization.OrgType.FOOD_BANK,
                contact_email="operations@metrorelief.org",
                contact_phone="+1-555-0199",
                address="100 Humanitarian Way, Suite 400",
            )

        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.filter(role=User.Role.ADMIN).first()

        donor_user = User.objects.filter(role=User.Role.DONOR).first()

        self.stdout.write(f"Assigning stock to organization: '{org.name}'")

        # 2. Categories
        categories_data = [
            (
                "Grains, Cereals & Staples",
                "Essential bulk carbohydrates, flour, grains, and dry pulses.",
            ),
            (
                "Canned & Preserved Foods",
                "Long shelf-life proteins, canned soups, vegetables, and spreads.",
            ),
            (
                "Fresh Dairy & Perishables",
                "Perishable cold-chain dairy, baked loaves, and fresh produce.",
            ),
            (
                "Infant Care & Nutrition",
                "Baby formula, diapers, wipes, and pediatric hygiene supplies.",
            ),
            (
                "Personal Hygiene & Sanitation",
                "Soap, oral care, sanitizers, and family hygiene packages.",
            ),
            (
                "Medical & First Aid Supplies",
                "Emergency medical kits, pain relief, and hydration salts.",
            ),
            (
                "Emergency Bedding & Shelter",
                "Thermal blankets, tarpaulins, and shelter emergency supplies.",
            ),
        ]

        categories = {}
        for cat_name, desc in categories_data:
            cat, _ = Category.objects.get_or_create(name=cat_name, defaults={"description": desc})
            categories[cat_name] = cat

        # 3. Inventory Items Catalog
        items_spec = [
            # Grains & Staples
            (
                "Fortified Long Grain Rice (kg)",
                "Grains, Cereals & Staples",
                "kg",
                False,
                Decimal("100.00"),
                Decimal("450.00"),
            ),
            (
                "Whole Wheat Flour (10kg Bags)",
                "Grains, Cereals & Staples",
                "bags",
                False,
                Decimal("30.00"),
                Decimal("110.00"),
            ),
            (
                "Rolled Oats Cereal (Boxes)",
                "Grains, Cereals & Staples",
                "boxes",
                False,
                Decimal("25.00"),
                Decimal("75.00"),
            ),
            (
                "Fortified Pasta Spaghetti (Packs)",
                "Grains, Cereals & Staples",
                "packs",
                False,
                Decimal("40.00"),
                Decimal("140.00"),
            ),
            (
                "Dry Red Lentils & Pulses (kg)",
                "Grains, Cereals & Staples",
                "kg",
                False,
                Decimal("50.00"),
                Decimal("200.00"),
            ),
            # Canned & Preserved
            (
                "Canned Tuna in Water 185g",
                "Canned & Preserved Foods",
                "cans",
                False,
                Decimal("60.00"),
                Decimal("220.00"),
            ),
            (
                "Canned Tomato & Veg Soup 400g",
                "Canned & Preserved Foods",
                "cans",
                False,
                Decimal("40.00"),
                Decimal("12.00"),
            ),  # LOW STOCK
            (
                "Canned Black Beans 400g",
                "Canned & Preserved Foods",
                "cans",
                False,
                Decimal("45.00"),
                Decimal("175.00"),
            ),
            (
                "Canned Sweet Corn Kernels",
                "Canned & Preserved Foods",
                "cans",
                False,
                Decimal("50.00"),
                Decimal("15.00"),
            ),  # LOW STOCK
            (
                "Creamy Peanut Butter 500g",
                "Canned & Preserved Foods",
                "jars",
                False,
                Decimal("20.00"),
                Decimal("70.00"),
            ),
            # Fresh Dairy & Perishables (with expiry)
            (
                "Fresh Pasteurized Whole Milk (L)",
                "Fresh Dairy & Perishables",
                "liters",
                True,
                Decimal("15.00"),
                Decimal("35.00"),
            ),  # EXPIRING SOON
            (
                "Cheddar Cheese Blocks 500g",
                "Fresh Dairy & Perishables",
                "blocks",
                True,
                Decimal("10.00"),
                Decimal("26.00"),
            ),  # EXPIRING SOON
            (
                "Fresh Red Apples (5kg Crates)",
                "Fresh Dairy & Perishables",
                "crates",
                True,
                Decimal("8.00"),
                Decimal("15.00"),
            ),  # EXPIRING SOON
            (
                "Whole Wheat Sliced Bread",
                "Fresh Dairy & Perishables",
                "loaves",
                True,
                Decimal("20.00"),
                Decimal("6.00"),
            ),  # LOW STOCK & EXPIRING SOON
            # Infant Care
            (
                "Infant Formula Stage 1 (800g)",
                "Infant Care & Nutrition",
                "tins",
                False,
                Decimal("20.00"),
                Decimal("60.00"),
            ),
            (
                "Baby Diapers Size 3 (56ct)",
                "Infant Care & Nutrition",
                "packs",
                False,
                Decimal("25.00"),
                Decimal("75.00"),
            ),
            (
                "Hypoallergenic Baby Wipes (80ct)",
                "Infant Care & Nutrition",
                "packs",
                False,
                Decimal("30.00"),
                Decimal("110.00"),
            ),
            # Personal Hygiene
            (
                "Antiseptic Bath Soap (Bars)",
                "Personal Hygiene & Sanitation",
                "bars",
                False,
                Decimal("50.00"),
                Decimal("250.00"),
            ),
            (
                "Fluoride Toothpaste (100ml)",
                "Personal Hygiene & Sanitation",
                "tubes",
                False,
                Decimal("30.00"),
                Decimal("130.00"),
            ),
            (
                "Complete Family Hygiene Kit",
                "Personal Hygiene & Sanitation",
                "kits",
                False,
                Decimal("15.00"),
                Decimal("40.00"),
            ),
            (
                "Disinfectant Hand Gel 500ml",
                "Personal Hygiene & Sanitation",
                "bottles",
                False,
                Decimal("20.00"),
                Decimal("80.00"),
            ),
            # Medical & First Aid
            (
                "Emergency First Aid Trauma Kit",
                "Medical & First Aid Supplies",
                "kits",
                False,
                Decimal("10.00"),
                Decimal("30.00"),
            ),
            (
                "Paracetamol Tablets 500mg",
                "Medical & First Aid Supplies",
                "packs",
                False,
                Decimal("25.00"),
                Decimal("7.00"),
            ),  # LOW STOCK
            (
                "Oral Rehydration Salts (ORS)",
                "Medical & First Aid Supplies",
                "packets",
                False,
                Decimal("40.00"),
                Decimal("160.00"),
            ),
            # Bedding & Shelter
            (
                "Thermal Mylar Emergency Blankets",
                "Emergency Bedding & Shelter",
                "units",
                False,
                Decimal("30.00"),
                Decimal("95.00"),
            ),
            (
                "Heavy-Duty Rain Tarpaulins 4x5m",
                "Emergency Bedding & Shelter",
                "units",
                False,
                Decimal("10.00"),
                Decimal("25.00"),
            ),
        ]

        today = timezone.now().date()

        # 4. Create or Update Inventory Items and Inbound Donations
        donation_food, _ = Donation.objects.get_or_create(
            organization=org,
            donor_name="Global Food Relief Partners",
            date_received=today - timedelta(days=5),
            defaults={
                "donor_contact": "intake@globalfoodrelief.test",
                "notes": "Bulk humanitarian dry goods and staples container intake.",
                "recorded_by": admin_user,
            },
        )

        donation_donor, _ = Donation.objects.get_or_create(
            organization=org,
            donor_name="Community Care Foundation",
            donor_user=donor_user,
            date_received=today - timedelta(days=3),
            defaults={
                "donor_contact": "liaison@communitycare.test",
                "notes": "Community infant care, hygiene packages, and emergency medical kits.",
                "recorded_by": admin_user,
            },
        )

        donation_fresh, _ = Donation.objects.get_or_create(
            organization=org,
            donor_name="Valley Farm Producers Cooperative",
            date_received=today - timedelta(days=1),
            defaults={
                "donor_contact": "dispatch@valleyfarms.test",
                "notes": "Direct refrigerated farm intake: fresh milk, artisan cheese, bread, and apples.",
                "recorded_by": admin_user,
            },
        )

        created_items = {}
        for name, cat_name, unit, perishable, threshold, target_stock in items_spec:
            item, _ = InventoryItem.objects.get_or_create(
                organization=org,
                name=name,
                defaults={
                    "category": categories[cat_name],
                    "unit_of_measure": unit,
                    "is_perishable": perishable,
                    "reorder_threshold": threshold,
                },
            )
            # Ensure attributes match
            item.category = categories[cat_name]
            item.unit_of_measure = unit
            item.is_perishable = perishable
            item.reorder_threshold = threshold
            item.save()

            current_stock = item.get_current_stock()
            needed_stock = target_stock - current_stock
            if needed_stock > 0:
                # Assign appropriate donation source and expiry
                expiry = None
                donor_obj = donation_food
                if perishable:
                    donor_obj = donation_fresh
                    if "Milk" in name:
                        expiry = today + timedelta(days=3)
                    elif "Bread" in name:
                        expiry = today + timedelta(days=2)
                    elif "Apples" in name:
                        expiry = today + timedelta(days=4)
                    elif "Cheese" in name:
                        expiry = today + timedelta(days=6)
                elif (
                    "Baby" in name
                    or "Hygiene" in name
                    or "First Aid" in name
                    or "Paracetamol" in name
                    or "ORS" in name
                ):
                    donor_obj = donation_donor

                StockTransaction.objects.create(
                    inventory_item=item,
                    organization=org,
                    transaction_type=StockTransaction.TransactionType.DONATION_IN,
                    quantity=needed_stock,
                    recorded_by=admin_user,
                    donation=donor_obj,
                    expiry_date=expiry,
                    note=f"Initial audited stock intake for {name}.",
                )
            created_items[name] = item

        # 5. Realistic Distribution Requests (Pending, Approved, Fulfilled)
        # Request 1: Pending Review
        req_pending, _ = DistributionRequest.objects.get_or_create(
            organization=org,
            recipient_name="St. Jude Emergency Shelter",
            status=DistributionRequest.Status.PENDING,
            defaults={
                "recipient_contact": "caseworker@stjudeshelter.org",
                "requested_by": admin_user,
                "notes": "Emergency relief requisition for 12 incoming displaced families.",
            },
        )
        if not req_pending.items.exists():
            DistributionRequestItem.objects.create(
                distribution_request=req_pending,
                inventory_item=created_items["Fortified Long Grain Rice (kg)"],
                quantity_requested=Decimal("50.00"),
            )
            DistributionRequestItem.objects.create(
                distribution_request=req_pending,
                inventory_item=created_items["Canned Tuna in Water 185g"],
                quantity_requested=Decimal("40.00"),
            )
            DistributionRequestItem.objects.create(
                distribution_request=req_pending,
                inventory_item=created_items["Baby Diapers Size 3 (56ct)"],
                quantity_requested=Decimal("15.00"),
            )

        # Request 2: Approved for Fulfillment
        req_approved, _ = DistributionRequest.objects.get_or_create(
            organization=org,
            recipient_name="Hope Community Soup Kitchen",
            status=DistributionRequest.Status.APPROVED,
            defaults={
                "recipient_contact": "kitchen-manager@hopekitchen.org",
                "requested_by": admin_user,
                "reviewed_by": admin_user,
                "reviewed_at": timezone.now(),
                "notes": "Approved standard monthly relief allocation for 300 daily meal covers.",
            },
        )
        if not req_approved.items.exists():
            DistributionRequestItem.objects.create(
                distribution_request=req_approved,
                inventory_item=created_items["Fortified Pasta Spaghetti (Packs)"],
                quantity_requested=Decimal("60.00"),
            )
            DistributionRequestItem.objects.create(
                distribution_request=req_approved,
                inventory_item=created_items["Canned Black Beans 400g"],
                quantity_requested=Decimal("50.00"),
            )

        # Request 3: Fulfilled Relief Dispatch
        req_fulfilled, _ = DistributionRequest.objects.get_or_create(
            organization=org,
            recipient_name="Westside Disaster Evacuation Hub",
            status=DistributionRequest.Status.FULFILLED,
            defaults={
                "recipient_contact": "coordination@westsidehub.org",
                "requested_by": admin_user,
                "reviewed_by": admin_user,
                "reviewed_at": timezone.now() - timedelta(days=2),
                "notes": "Complete emergency relief kits and blankets dispatched.",
            },
        )
        if not req_fulfilled.items.exists():
            blanket_item = created_items["Thermal Mylar Emergency Blankets"]
            DistributionRequestItem.objects.create(
                distribution_request=req_fulfilled,
                inventory_item=blanket_item,
                quantity_requested=Decimal("20.00"),
                quantity_fulfilled=Decimal("20.00"),
            )
            StockTransaction.objects.create(
                inventory_item=blanket_item,
                organization=org,
                transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
                quantity=Decimal("20.00"),
                recorded_by=admin_user,
                distribution_request=req_fulfilled,
                note="Dispatched 20 thermal blankets to Westside Evacuation Hub.",
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Successfully seeded comprehensive relief inventory stocks and workflows!"
            )
        )
