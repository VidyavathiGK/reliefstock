from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render

from accounts.decorators import donor_required
from inventory.models import Donation


@login_required
def home(request):
    """
    Landing page dispatcher:
    - DONOR role users are redirected to their personal Donor Portal.
    - Staff, Admin, and Volunteer users see the operational overview / quick navigation.
    """
    user = request.user
    if user.role == "DONOR" and not user.is_superuser:
        return redirect("donor_portal")

    return render(
        request,
        "home.html",
        {
            "user": user,
        },
    )


@donor_required
def donor_portal(request):
    """
    Read-only view for DONOR role users showing their personal donation history and receipts.
    Strictly isolated: donors can never view other donors' data or staff inventory.
    """
    user = request.user
    donations = (
        Donation.objects.filter(
            Q(donor_user=user)
            | Q(donor_contact__iexact=user.email)
            | Q(donor_name__iexact=user.username)
        )
        .select_related("organization")
        .prefetch_related("stock_transactions__inventory_item")
        .distinct()
        .order_by("-date_received", "-created_at")
    )

    total_donations_count = donations.count()

    return render(
        request,
        "accounts/donor_portal.html",
        {
            "user": user,
            "donations": donations,
            "total_donations_count": total_donations_count,
        },
    )
