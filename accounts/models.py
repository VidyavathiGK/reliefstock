from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.

    Provides role-based categorization (ADMIN, STAFF, VOLUNTEER, DONOR)
    and an optional link to an Organization. Subclassing AbstractUser early
    is a Django best practice that allows extending the user model without
    risking painful database refactoring later.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        STAFF = "STAFF", "Staff Member"
        VOLUNTEER = "VOLUNTEER", "Volunteer"
        DONOR = "DONOR", "Donor"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VOLUNTEER,
        help_text="Role designation defining permissions and UI access tiers across ReliefStock.",
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Direct phone number for urgent dispatch, scheduling, or donor coordination.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        help_text="Organization with which this user is affiliated. Can be null for donors or platform admins.",
    )

    class Meta:
        ordering = ["username"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        org_name = f" - {self.organization.name}" if self.organization else ""
        return f"{self.username} [{self.get_role_display()}]{org_name}"
