from django.test import TestCase

from organizations.models import Organization


class OrganizationModelTests(TestCase):
    """
    Test suite for Organization model.
    """

    def test_organization_creation(self):
        org = Organization.objects.create(
            name="Shelter of Hope",
            org_type=Organization.OrgType.SHELTER,
            address="456 Beacon Blvd",
            contact_email="hope@shelter.org",
            contact_phone="555-0155",
        )
        self.assertEqual(str(org), "Shelter of Hope (Emergency Shelter)")
        self.assertEqual(org.org_type, "SHELTER")
        self.assertIsNotNone(org.created_at)
