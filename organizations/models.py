from django.db import models


class Organization(models.Model):
    """
    Represents an entity operating in relief, donation, or inventory distribution,
    such as emergency shelters, local food banks, or charitable NGOs.

    One organization can have many staff and volunteer users associated with it.
    """

    class OrgType(models.TextChoices):
        SHELTER = "SHELTER", "Emergency Shelter"
        FOOD_BANK = "FOOD_BANK", "Food Bank / Pantry"
        NGO = "NGO", "Non-Governmental Organization"

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Official name of the organization (e.g., 'City Hope Shelter').",
    )
    org_type = models.CharField(
        max_length=20,
        choices=OrgType.choices,
        default=OrgType.FOOD_BANK,
        help_text="Classification defining the organization's primary community function.",
    )
    address = models.TextField(help_text="Physical facility address or headquarters location.")
    contact_email = models.EmailField(
        help_text="Primary email address for administrative and logistics contact."
    )
    contact_phone = models.CharField(
        max_length=20, help_text="Direct phone line for coordination and emergency dispatch."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Audit timestamp indicating when this organization record was created.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return f"{self.name} ({self.get_org_type_display()})"
