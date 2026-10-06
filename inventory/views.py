from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import (
    admin_required,
    staff_or_admin_required,
    volunteer_or_staff_required,
)

from .forms import (
    DateRangeReportFilterForm,
    DistributionFulfillmentForm,
    DistributionRequestHeaderForm,
    DistributionRequestItemFormSet,
    DistributionReviewForm,
    DonationHeaderForm,
    DonationItemFormSet,
    ManualStockAdjustmentForm,
)
from .models import (
    Category,
    DistributionRequest,
    DistributionRequestItem,
    Donation,
    InventoryItem,
    StockTransaction,
)
from .reports import export_as_csv, export_as_pdf


@staff_or_admin_required
def inventory_list(request):
    """
    Shows all InventoryItems for the logged-in user's organization along with
    their current stock quantity, unit, and category.

    Optimized: Stock for all items is derived in a single SQL query using Sum/Case/When.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    items = (
        InventoryItem.objects.filter(organization=user_org)
        .select_related("category")
        .annotate(
            current_stock=Coalesce(
                Sum(
                    Case(
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.DONATION_IN,
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                            ],
                            then=F("stock_transactions__quantity"),
                        ),
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                                StockTransaction.TransactionType.DISTRIBUTION_OUT,
                            ],
                            then=-F("stock_transactions__quantity"),
                        ),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0.00"), output_field=DecimalField()),
            )
        )
        .order_by("category__name", "name")
    )

    categories = Category.objects.filter(items__organization=user_org).distinct().order_by("name")

    return render(
        request,
        "inventory/inventory_list.html",
        {
            "items": items,
            "organization": user_org,
            "categories": categories,
        },
    )


@staff_or_admin_required
def inventory_detail(request, pk):
    """
    Displays an inventory item's metadata, current stock, and full
    chronological audit history of stock transactions.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    item = get_object_or_404(InventoryItem, pk=pk, organization=user_org)
    current_stock = item.get_current_stock()
    transactions = item.stock_transactions.select_related(
        "recorded_by", "donation", "distribution_request"
    ).order_by("created_at")

    return render(
        request,
        "inventory/inventory_detail.html",
        {
            "item": item,
            "current_stock": current_stock,
            "transactions": transactions,
        },
    )


@volunteer_or_staff_required
def record_donation(request):
    """
    Allows staff or volunteers to log incoming donations with one or more
    items and quantities in a single atomic transaction.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    if request.method == "POST":
        header_form = DonationHeaderForm(request.POST)
        formset = DonationItemFormSet(request.POST, form_kwargs={"organization": user_org})

        if header_form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # 1. Create the parent donation header
                donation = header_form.save(commit=False)
                donation.organization = user_org
                donation.recorded_by = request.user
                donation.save()

                # 2. Create the child StockTransaction records
                item_count = 0
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                        item = form.cleaned_data.get("inventory_item")
                        qty = form.cleaned_data.get("quantity")
                        if item and qty:
                            StockTransaction.objects.create(
                                inventory_item=item,
                                transaction_type=StockTransaction.TransactionType.DONATION_IN,
                                quantity=qty,
                                recorded_by=request.user,
                                organization=user_org,
                                donation=donation,
                                expiry_date=form.cleaned_data.get("expiry_date"),
                                note=form.cleaned_data.get("note", ""),
                            )
                            item_count += 1

                donor_label = donation.donor_name if donation.donor_name else "Anonymous Donor"
                messages.success(
                    request,
                    f"Donation #{donation.pk} from {donor_label} recorded successfully with {item_count} item(s).",
                )

                # Volunteers cannot view inventory lists, redirect them cleanly
                if request.user.role == "VOLUNTEER" and not request.user.is_superuser:
                    return redirect("inventory:record_donation")
                return redirect("inventory:inventory_list")
    else:
        header_form = DonationHeaderForm()
        formset = DonationItemFormSet(form_kwargs={"organization": user_org})

    return render(
        request,
        "inventory/record_donation.html",
        {
            "header_form": header_form,
            "formset": formset,
            "organization": user_org,
        },
    )


@staff_or_admin_required
def manual_adjustment(request, pk):
    """
    Allows staff or admin to correct stock counts upwards or downwards.
    Requires an explicit explanation note for audit compliance.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    item = get_object_or_404(InventoryItem, pk=pk, organization=user_org)
    current_stock = item.get_current_stock()

    if request.method == "POST":
        form = ManualStockAdjustmentForm(request.POST, inventory_item=item)
        if form.is_valid():
            with transaction.atomic():
                txn_type = form.cleaned_data["transaction_type"]
                qty = form.cleaned_data["quantity"]
                note = form.cleaned_data["note"]
                expiry_date = form.cleaned_data.get("expiry_date")

                StockTransaction.objects.create(
                    inventory_item=item,
                    transaction_type=txn_type,
                    quantity=qty,
                    recorded_by=request.user,
                    organization=user_org,
                    note=note,
                    expiry_date=expiry_date,
                )

                direction = (
                    "added"
                    if txn_type == StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN
                    else "deducted"
                )
                messages.success(
                    request,
                    f"Successfully {direction} {qty} {item.unit_of_measure} for '{item.name}'.",
                )
                return redirect("inventory:inventory_detail", pk=item.pk)
    else:
        form = ManualStockAdjustmentForm(inventory_item=item)

    return render(
        request,
        "inventory/manual_adjustment.html",
        {
            "item": item,
            "form": form,
            "current_stock": current_stock,
        },
    )


@volunteer_or_staff_required
def distribution_request_create(request):
    """
    Allows volunteers or staff to submit a new distribution request for a
    recipient/program with one or more items.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    if request.method == "POST":
        header_form = DistributionRequestHeaderForm(request.POST)
        formset = DistributionRequestItemFormSet(
            request.POST, form_kwargs={"organization": user_org}
        )

        if header_form.is_valid() and formset.is_valid():
            with transaction.atomic():
                dist_req = header_form.save(commit=False)
                dist_req.organization = user_org
                dist_req.requested_by = request.user
                dist_req.status = DistributionRequest.Status.PENDING
                dist_req.save()

                item_count = 0
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                        item = form.cleaned_data.get("inventory_item")
                        qty = form.cleaned_data.get("quantity_requested")
                        if item and qty:
                            DistributionRequestItem.objects.create(
                                distribution_request=dist_req,
                                inventory_item=item,
                                quantity_requested=qty,
                                quantity_fulfilled=Decimal("0.00"),
                            )
                            item_count += 1

                messages.success(
                    request,
                    f"Distribution Request #{dist_req.pk} for '{dist_req.recipient_name}' submitted successfully with {item_count} item(s).",
                )
                return redirect("inventory:distribution_request_detail", pk=dist_req.pk)
    else:
        header_form = DistributionRequestHeaderForm()
        formset = DistributionRequestItemFormSet(form_kwargs={"organization": user_org})

    return render(
        request,
        "inventory/distribution_request_form.html",
        {
            "header_form": header_form,
            "formset": formset,
            "organization": user_org,
        },
    )


@volunteer_or_staff_required
def distribution_request_list(request):
    """
    Lists distribution requests for the user's organization.
    Supports filtering by status (PENDING, APPROVED, REJECTED, FULFILLED).
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    status_filter = request.GET.get("status", "").upper()
    valid_statuses = dict(DistributionRequest.Status.choices)

    requests_qs = (
        DistributionRequest.objects.filter(organization=user_org)
        .select_related("requested_by", "reviewed_by")
        .prefetch_related("items__inventory_item")
    )

    if status_filter in valid_statuses:
        requests_qs = requests_qs.filter(status=status_filter)

    return render(
        request,
        "inventory/distribution_request_list.html",
        {
            "requests": requests_qs,
            "current_status": status_filter,
            "status_choices": DistributionRequest.Status.choices,
            "organization": user_org,
        },
    )


@volunteer_or_staff_required
def distribution_request_detail(request, pk):
    """
    Displays the details of a single distribution request, including its line items,
    status, fulfillment progress, and audit history.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    dist_req = get_object_or_404(DistributionRequest, pk=pk, organization=user_org)
    items = dist_req.items.select_related("inventory_item", "inventory_item__category").all()

    items_with_stock = []
    for line in items:
        items_with_stock.append(
            {
                "line": line,
                "current_stock": line.inventory_item.get_current_stock(),
            }
        )

    transactions = dist_req.stock_transactions.select_related(
        "inventory_item", "recorded_by"
    ).order_by("created_at")

    return render(
        request,
        "inventory/distribution_request_detail.html",
        {
            "dist_req": dist_req,
            "items_with_stock": items_with_stock,
            "transactions": transactions,
            "is_admin": request.user.role == "ADMIN" or request.user.is_superuser,
            "is_staff_or_admin": request.user.role in ["STAFF", "ADMIN"]
            or request.user.is_superuser,
        },
    )


@admin_required
def distribution_request_review(request, pk):
    """
    ADMIN-only review view to approve or reject a pending distribution request.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    dist_req = get_object_or_404(DistributionRequest, pk=pk, organization=user_org)

    if dist_req.status != DistributionRequest.Status.PENDING:
        messages.info(
            request,
            f"Request #{dist_req.pk} is already '{dist_req.get_status_display()}' and cannot be reviewed.",
        )
        return redirect("inventory:distribution_request_detail", pk=dist_req.pk)

    if request.method == "POST":
        form = DistributionReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            review_notes = form.cleaned_data.get("review_notes", "").strip()

            dist_req.reviewed_by = request.user
            dist_req.reviewed_at = timezone.now()

            if action == "APPROVE":
                dist_req.status = DistributionRequest.Status.APPROVED
                action_label = "Approved"
            else:
                dist_req.status = DistributionRequest.Status.REJECTED
                action_label = "Rejected"

            if review_notes:
                timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                note_addition = (
                    f"[{action_label} by {request.user.username} on {timestamp}: {review_notes}]"
                )
                if dist_req.notes:
                    dist_req.notes += f"\n{note_addition}"
                else:
                    dist_req.notes = note_addition

            dist_req.save()
            messages.success(request, f"Request #{dist_req.pk} has been {action_label.lower()}.")
            return redirect("inventory:distribution_request_detail", pk=dist_req.pk)
    else:
        form = DistributionReviewForm()

    return render(
        request,
        "inventory/distribution_review.html",
        {
            "dist_req": dist_req,
            "form": form,
        },
    )


@staff_or_admin_required
def distribution_request_fulfill(request, pk):
    """
    STAFF or ADMIN fulfillment view for APPROVED distribution requests.
    Validates stock availability, generates StockTransaction(DISTRIBUTION_OUT) records,
    and updates line item fulfilled amounts. Supports partial fulfillment if stock
    is insufficient or only partially dispatched.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    dist_req = get_object_or_404(DistributionRequest, pk=pk, organization=user_org)

    if dist_req.status != DistributionRequest.Status.APPROVED:
        messages.warning(
            request,
            f"Request #{dist_req.pk} has status '{dist_req.get_status_display()}'. Only Approved requests can be fulfilled.",
        )
        return redirect("inventory:distribution_request_detail", pk=dist_req.pk)

    if request.method == "POST":
        form = DistributionFulfillmentForm(request.POST, distribution_request=dist_req)
        if form.is_valid():
            fulfillment_note = form.cleaned_data.get("fulfillment_note", "").strip()
            total_dispatched_items = 0

            with transaction.atomic():
                for line_item in dist_req.items.select_related("inventory_item").all():
                    qty_to_dispatch = form.cleaned_data.get(f"fulfill_item_{line_item.id}")
                    if qty_to_dispatch and qty_to_dispatch > Decimal("0.00"):
                        StockTransaction.objects.create(
                            inventory_item=line_item.inventory_item,
                            transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
                            quantity=qty_to_dispatch,
                            recorded_by=request.user,
                            organization=user_org,
                            distribution_request=dist_req,
                            note=fulfillment_note
                            or f"Fulfillment for Request #{dist_req.pk} ({dist_req.recipient_name})",
                        )
                        line_item.quantity_fulfilled = (
                            line_item.quantity_fulfilled or Decimal("0.00")
                        ) + qty_to_dispatch
                        line_item.save()
                        total_dispatched_items += 1

                # Evaluate overall fulfillment completion
                all_items = list(dist_req.items.all())
                is_all_fulfilled = all(item.is_fully_fulfilled for item in all_items)

                if is_all_fulfilled:
                    dist_req.status = DistributionRequest.Status.FULFILLED
                    status_msg = f"Request #{dist_req.pk} has been completely fulfilled!"
                else:
                    dist_req.status = DistributionRequest.Status.APPROVED
                    remaining_desc = ", ".join(
                        [
                            f"{it.inventory_item.name}: {it.quantity_remaining} {it.inventory_item.unit_of_measure} remaining"
                            for it in all_items
                            if not it.is_fully_fulfilled
                        ]
                    )
                    timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                    audit_log = f"[Partial dispatch by {request.user.username} on {timestamp}: {remaining_desc}]"
                    if dist_req.notes:
                        dist_req.notes += f"\n{audit_log}"
                    else:
                        dist_req.notes = audit_log
                    status_msg = f"Request #{dist_req.pk} was partially fulfilled. Status remains Approved ({remaining_desc})."

                dist_req.save()

            if is_all_fulfilled:
                messages.success(request, status_msg)
            else:
                messages.warning(request, status_msg)

            return redirect("inventory:distribution_request_detail", pk=dist_req.pk)
    else:
        form = DistributionFulfillmentForm(distribution_request=dist_req)

    lines_info = []
    for line in dist_req.items.select_related("inventory_item").all():
        field_name = f"fulfill_item_{line.id}"
        lines_info.append(
            {
                "line": line,
                "current_stock": line.inventory_item.get_current_stock(),
                "field": form[field_name] if field_name in form.fields else None,
            }
        )

    return render(
        request,
        "inventory/distribution_fulfill.html",
        {
            "dist_req": dist_req,
            "form": form,
            "lines_info": lines_info,
        },
    )


@staff_or_admin_required
def expiring_stock_list(request):
    """
    Displays perishable items nearing expiration or already expired.
    - 'expiring_soon' (default): expiring within the next 7 days (today <= expiry_date <= today + 7).
    - 'expired': expiry_date < today.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    view_mode = request.GET.get("filter", "expiring_soon")
    today = timezone.localdate()
    seven_days = today + timedelta(days=7)

    base_txns = StockTransaction.objects.filter(
        organization=user_org, inventory_item__is_perishable=True, expiry_date__isnull=False
    ).select_related("inventory_item", "inventory_item__category", "donation", "recorded_by")

    if view_mode == "expired":
        transactions = base_txns.filter(expiry_date__lt=today).order_by("expiry_date")
    else:
        view_mode = "expiring_soon"
        transactions = base_txns.filter(
            expiry_date__gte=today, expiry_date__lte=seven_days
        ).order_by("expiry_date")

    annotated_txns = []
    for txn in transactions:
        days_diff = (txn.expiry_date - today).days
        annotated_txns.append(
            {
                "txn": txn,
                "days_diff": days_diff,
                "is_overdue": days_diff < 0,
                "abs_days": abs(days_diff),
                "item_stock": txn.inventory_item.get_current_stock(),
            }
        )

    return render(
        request,
        "inventory/expiring_stock.html",
        {
            "annotated_txns": annotated_txns,
            "view_mode": view_mode,
            "today": today,
            "seven_days": seven_days,
            "organization": user_org,
        },
    )


@staff_or_admin_required
def low_stock_list(request):
    """
    Lists inventory items where the live stock count is at or below the configured
    reorder_threshold.
    """
    user_org = request.user.organization
    if not user_org:
        messages.warning(request, "Your user profile is not linked to any organization.")
        return redirect("home")

    items = (
        InventoryItem.objects.filter(organization=user_org, reorder_threshold__isnull=False)
        .select_related("category")
        .annotate(
            current_stock=Coalesce(
                Sum(
                    Case(
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.DONATION_IN,
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                            ],
                            then=F("stock_transactions__quantity"),
                        ),
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                                StockTransaction.TransactionType.DISTRIBUTION_OUT,
                            ],
                            then=-F("stock_transactions__quantity"),
                        ),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0.00"), output_field=DecimalField()),
            )
        )
        .filter(current_stock__lte=F("reorder_threshold"))
        .annotate(shortfall=F("reorder_threshold") - F("current_stock"))
        .order_by("-shortfall", "name")
    )

    return render(
        request,
        "inventory/low_stock.html",
        {
            "items": items,
            "organization": user_org,
        },
    )


@staff_or_admin_required
def dashboard(request):
    """
    Staff and Admin Executive Dashboard:
    Aggregates high-level inventory metrics, low-stock flags, perishables expiry,
    pending distribution requests, and monthly activity counts.
    Multi-tenant isolation strictly enforced by request.org.
    """
    user_org = getattr(request, "org", None) or request.user.organization
    today = timezone.localdate()
    seven_days = today + timedelta(days=7)

    # 1. Catalog & Stock aggregation
    item_qs = InventoryItem.objects.filter(organization=user_org)
    total_distinct_items = item_qs.count()

    annotated_items = item_qs.annotate(
        current_stock=Coalesce(
            Sum(
                Case(
                    When(
                        stock_transactions__transaction_type__in=[
                            StockTransaction.TransactionType.DONATION_IN,
                            StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                        ],
                        then=F("stock_transactions__quantity"),
                    ),
                    When(
                        stock_transactions__transaction_type__in=[
                            StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                            StockTransaction.TransactionType.DISTRIBUTION_OUT,
                        ],
                        then=-F("stock_transactions__quantity"),
                    ),
                    output_field=DecimalField(),
                )
            ),
            Value(Decimal("0.00"), output_field=DecimalField()),
        )
    )

    total_stock_units = sum(item.current_stock for item in annotated_items) or Decimal("0.00")
    low_stock_count = sum(
        1
        for item in annotated_items
        if item.reorder_threshold is not None and item.current_stock <= item.reorder_threshold
    )

    # 2. Perishable Expiry counts
    perishable_txns = StockTransaction.objects.filter(
        organization=user_org, inventory_item__is_perishable=True, expiry_date__isnull=False
    )
    expiring_soon_count = perishable_txns.filter(
        expiry_date__gte=today, expiry_date__lte=seven_days
    ).count()
    expired_count = perishable_txns.filter(expiry_date__lt=today).count()

    # 3. Pending review distribution requests
    pending_requests_count = DistributionRequest.objects.filter(
        organization=user_org, status=DistributionRequest.Status.PENDING
    ).count()

    # 4. Activity this month (Donations)
    month_donations = Donation.objects.filter(
        organization=user_org, date_received__year=today.year, date_received__month=today.month
    )
    donations_this_month_count = month_donations.count()
    items_donated_this_month = StockTransaction.objects.filter(
        organization=user_org,
        transaction_type=StockTransaction.TransactionType.DONATION_IN,
        donation__date_received__year=today.year,
        donation__date_received__month=today.month,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")

    # 5. Activity this month (Distributions)
    month_distributions = DistributionRequest.objects.filter(
        organization=user_org,
        status=DistributionRequest.Status.FULFILLED,
        reviewed_at__year=today.year,
        reviewed_at__month=today.month,
    )
    distributions_this_month_count = month_distributions.count()
    items_distributed_this_month = StockTransaction.objects.filter(
        organization=user_org,
        transaction_type=StockTransaction.TransactionType.DISTRIBUTION_OUT,
        created_at__year=today.year,
        created_at__month=today.month,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")

    # 6. Critical Low Stock items (sorted by largest shortfall)
    critical_low_stock_items = []
    for item in annotated_items:
        if item.reorder_threshold is not None and item.current_stock <= item.reorder_threshold:
            shortfall = item.reorder_threshold - item.current_stock
            item.shortfall = shortfall
            critical_low_stock_items.append(item)
    critical_low_stock_items.sort(key=lambda x: x.shortfall, reverse=True)
    critical_low_stock_items = critical_low_stock_items[:5]

    # 7. Recent Pending Distribution Requests
    recent_pending_requests = (
        DistributionRequest.objects.filter(
            organization=user_org, status=DistributionRequest.Status.PENDING
        )
        .select_related("requested_by")
        .prefetch_related("items__inventory_item")
        .order_by("-requested_at")[:5]
    )

    # 8. Recent activity ledger
    recent_activity = (
        StockTransaction.objects.filter(organization=user_org)
        .select_related("inventory_item", "recorded_by", "donation", "distribution_request")
        .order_by("-created_at")[:6]
    )

    # 9. Category distribution breakdown
    cat_totals = {}
    for item in annotated_items:
        cat_name = item.category.name if item.category else "General"
        cat_totals[cat_name] = cat_totals.get(cat_name, Decimal("0.00")) + item.current_stock
    category_summary = []
    if total_stock_units > 0:
        for cname, cstock in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = round((float(cstock) / float(total_stock_units)) * 100, 1)
            category_summary.append({"name": cname, "stock": cstock, "pct": pct})

    return render(
        request,
        "inventory/dashboard.html",
        {
            "organization": user_org,
            "total_distinct_items": total_distinct_items,
            "total_stock_units": total_stock_units,
            "low_stock_count": low_stock_count,
            "expiring_soon_count": expiring_soon_count,
            "expired_count": expired_count,
            "pending_requests_count": pending_requests_count,
            "donations_this_month_count": donations_this_month_count,
            "items_donated_this_month": items_donated_this_month,
            "distributions_this_month_count": distributions_this_month_count,
            "items_distributed_this_month": items_distributed_this_month,
            "today": today,
            "critical_low_stock_items": critical_low_stock_items,
            "recent_pending_requests": recent_pending_requests,
            "recent_activity": recent_activity,
            "category_summary": category_summary,
        },
    )


@staff_or_admin_required
def report_inventory(request):
    """
    Inventory Stock Report:
    Displays all items and live stock levels for request.org.
    Supports CSV and PDF downloads reusing the same filtered dataset.
    """
    user_org = getattr(request, "org", None) or request.user.organization
    export_format = request.GET.get("format", "").lower()

    items = (
        InventoryItem.objects.filter(organization=user_org)
        .select_related("category")
        .annotate(
            current_stock=Coalesce(
                Sum(
                    Case(
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.DONATION_IN,
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_IN,
                            ],
                            then=F("stock_transactions__quantity"),
                        ),
                        When(
                            stock_transactions__transaction_type__in=[
                                StockTransaction.TransactionType.MANUAL_ADJUSTMENT_OUT,
                                StockTransaction.TransactionType.DISTRIBUTION_OUT,
                            ],
                            then=-F("stock_transactions__quantity"),
                        ),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0.00"), output_field=DecimalField()),
            )
        )
        .order_by("category__name", "name")
    )

    headers = [
        "Item Name",
        "Category",
        "Current Stock",
        "Unit",
        "Perishable",
        "Reorder Threshold",
        "Stock Status",
    ]
    rows = []
    for item in items:
        status = "Normal"
        if item.reorder_threshold is not None:
            if item.current_stock <= Decimal("0.00"):
                status = "OUT OF STOCK"
            elif item.current_stock <= item.reorder_threshold:
                status = f"LOW STOCK (<= {item.reorder_threshold})"

        rows.append(
            [
                item.name,
                item.category.name,
                f"{item.current_stock}",
                item.unit_of_measure,
                "Yes" if item.is_perishable else "No",
                f"{item.reorder_threshold}" if item.reorder_threshold is not None else "None",
                status,
            ]
        )

    if export_format == "csv":
        return export_as_csv(
            f"inventory_report_{user_org.name.replace(' ', '_').lower()}", headers, rows
        )
    elif export_format == "pdf":
        summary = f"Total Items: {len(rows)} | Total Stock Units: {sum(item.current_stock for item in items)}"
        return export_as_pdf(
            f"inventory_report_{user_org.name.replace(' ', '_').lower()}",
            "Inventory Stock Report",
            user_org.name,
            headers,
            rows,
            col_widths=[140, 90, 70, 50, 55, 75, 90],
            summary_text=summary,
        )

    return render(
        request,
        "inventory/report_inventory.html",
        {
            "items": items,
            "organization": user_org,
        },
    )


@staff_or_admin_required
def report_donations(request):
    """
    Donation History Report:
    Shows donations received by request.org, with date range and keyword filtering.
    Exportable to CSV and PDF reusing the exact same filtered query.
    """
    user_org = getattr(request, "org", None) or request.user.organization
    export_format = request.GET.get("format", "").lower()

    form = DateRangeReportFilterForm(request.GET)
    donations = (
        Donation.objects.filter(organization=user_org)
        .select_related("recorded_by", "donor_user")
        .prefetch_related("stock_transactions__inventory_item")
        .order_by("-date_received", "-created_at")
    )

    if form.is_valid():
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")
        query = form.cleaned_data.get("query")

        if start_date:
            donations = donations.filter(date_received__gte=start_date)
        if end_date:
            donations = donations.filter(date_received__lte=end_date)
        if query:
            donations = donations.filter(
                Q(donor_name__icontains=query)
                | Q(donor_contact__icontains=query)
                | Q(notes__icontains=query)
                | Q(donor_user__username__icontains=query)
            )

    headers = [
        "Donation ID",
        "Date Received",
        "Donor Name",
        "Contact",
        "Registered User",
        "Items & Quantities",
        "Recorded By",
        "Notes",
    ]
    rows = []
    for d in donations:
        items_summary = (
            "; ".join(
                [
                    f"{txn.inventory_item.name}: {txn.quantity} {txn.inventory_item.unit_of_measure}"
                    for txn in d.stock_transactions.all()
                ]
            )
            or "No items logged"
        )
        rows.append(
            [
                f"#{d.pk}",
                d.date_received,
                d.donor_name or "Anonymous",
                d.donor_contact or "—",
                d.donor_user.username if d.donor_user else "—",
                items_summary,
                d.recorded_by.username,
                d.notes or "—",
            ]
        )

    if export_format == "csv":
        return export_as_csv(
            f"donation_history_{user_org.name.replace(' ', '_').lower()}", headers, rows
        )
    elif export_format == "pdf":
        summary = f"Total Donations: {len(rows)}"
        return export_as_pdf(
            f"donation_history_{user_org.name.replace(' ', '_').lower()}",
            "Donation History Report",
            user_org.name,
            headers,
            rows,
            col_widths=[50, 60, 80, 75, 65, 130, 60, 60],
            orientation="landscape",
            summary_text=summary,
        )

    return render(
        request,
        "inventory/report_donations.html",
        {
            "donations": donations,
            "form": form,
            "organization": user_org,
        },
    )


@staff_or_admin_required
def report_distributions(request):
    """
    Distribution History Report:
    Lists fulfilled distribution requests for request.org with date range filtering.
    Exportable to CSV and PDF reusing the exact same filtered query.
    """
    user_org = getattr(request, "org", None) or request.user.organization
    export_format = request.GET.get("format", "").lower()

    form = DateRangeReportFilterForm(request.GET)
    distributions = (
        DistributionRequest.objects.filter(
            organization=user_org, status=DistributionRequest.Status.FULFILLED
        )
        .select_related("requested_by", "reviewed_by")
        .prefetch_related("items__inventory_item", "stock_transactions__inventory_item")
        .order_by("-requested_at")
    )

    if form.is_valid():
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")
        query = form.cleaned_data.get("query")

        if start_date:
            distributions = distributions.filter(requested_at__date__gte=start_date)
        if end_date:
            distributions = distributions.filter(requested_at__date__lte=end_date)
        if query:
            distributions = distributions.filter(
                Q(recipient_name__icontains=query)
                | Q(recipient_contact__icontains=query)
                | Q(notes__icontains=query)
            )

    headers = [
        "Request ID",
        "Date Requested",
        "Date Reviewed",
        "Recipient",
        "Contact",
        "Items Fulfilled",
        "Requested By",
        "Reviewed By",
        "Notes",
    ]
    rows = []
    for dist in distributions:
        items_summary = (
            "; ".join(
                [
                    f"{it.inventory_item.name}: {it.quantity_fulfilled} {it.inventory_item.unit_of_measure}"
                    for it in dist.items.all()
                ]
            )
            or "—"
        )
        rows.append(
            [
                f"#{dist.pk}",
                dist.requested_at.strftime("%Y-%m-%d"),
                dist.reviewed_at.strftime("%Y-%m-%d") if dist.reviewed_at else "—",
                dist.recipient_name,
                dist.recipient_contact or "—",
                items_summary,
                dist.requested_by.username,
                dist.reviewed_by.username if dist.reviewed_by else "—",
                dist.notes or "—",
            ]
        )

    if export_format == "csv":
        return export_as_csv(
            f"distribution_history_{user_org.name.replace(' ', '_').lower()}", headers, rows
        )
    elif export_format == "pdf":
        summary = f"Total Fulfilled Distributions: {len(rows)}"
        return export_as_pdf(
            f"distribution_history_{user_org.name.replace(' ', '_').lower()}",
            "Distribution History Report",
            user_org.name,
            headers,
            rows,
            col_widths=[50, 65, 65, 80, 70, 130, 60, 60, 60],
            orientation="landscape",
            summary_text=summary,
        )

    return render(
        request,
        "inventory/report_distributions.html",
        {
            "distributions": distributions,
            "form": form,
            "organization": user_org,
        },
    )
