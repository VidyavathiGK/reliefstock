from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from organizations.models import Organization


class AccountsAndAuthTests(TestCase):
    """
    Test suite for Custom User model and Authentication flows.
    """

    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(
            name="Metro Relief Food Bank",
            org_type=Organization.OrgType.FOOD_BANK,
            address="123 River Road",
            contact_email="admin@metrorelief.org",
            contact_phone="555-0101",
        )
        self.user = User.objects.create_user(
            username="staff_alex",
            email="alex@metrorelief.org",
            password="StrongPassword123!",
            role=User.Role.STAFF,
            phone_number="555-0102",
            organization=self.org,
        )

    def test_custom_user_creation_and_attributes(self):
        """Verify custom user fields: role, phone_number, and organization."""
        self.assertEqual(self.user.username, "staff_alex")
        self.assertEqual(self.user.role, User.Role.STAFF)
        self.assertEqual(self.user.phone_number, "555-0102")
        self.assertEqual(self.user.organization, self.org)
        self.assertIn("staff_alex [Staff Member] - Metro Relief Food Bank", str(self.user))

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated requests to root URL must redirect to login."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_login_page_renders_successfully(self):
        """Login page must render with HTTP 200 and standard form."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log In")

    def test_authenticated_user_can_access_dashboard(self):
        """Logged-in users should see their username and role on the home dashboard."""
        self.client.login(username="staff_alex", password="StrongPassword123!")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        # Required format: "Logged in as {username} ({role})"
        self.assertContains(response, "Logged in as staff_alex (STAFF)")
        self.assertContains(response, "Metro Relief Food Bank")
