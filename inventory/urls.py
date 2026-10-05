from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    # Inventory item list & stock levels
    path("", views.inventory_list, name="inventory_list"),
    # Item detail & transaction audit history
    path("<int:pk>/", views.inventory_detail, name="inventory_detail"),
    # Manual stock count adjustment (in/out)
    path("<int:pk>/adjust/", views.manual_adjustment, name="manual_adjustment"),
    # Multi-item donation intake
    path("donations/record/", views.record_donation, name="record_donation"),
    # Distribution request workflow
    path("distributions/", views.distribution_request_list, name="distribution_request_list"),
    path(
        "distributions/create/",
        views.distribution_request_create,
        name="distribution_request_create",
    ),
    path(
        "distributions/<int:pk>/",
        views.distribution_request_detail,
        name="distribution_request_detail",
    ),
    path(
        "distributions/<int:pk>/review/",
        views.distribution_request_review,
        name="distribution_request_review",
    ),
    path(
        "distributions/<int:pk>/fulfill/",
        views.distribution_request_fulfill,
        name="distribution_request_fulfill",
    ),
    # Monitoring & alerts
    path("alerts/expiring/", views.expiring_stock_list, name="expiring_stock_list"),
    path("alerts/low-stock/", views.low_stock_list, name="low_stock_list"),
    # Executive Dashboard (Phase 4)
    path("dashboard/", views.dashboard, name="dashboard"),
    # Reports & Exports (Phase 4)
    path("reports/inventory/", views.report_inventory, name="report_inventory"),
    path("reports/donations/", views.report_donations, name="report_donations"),
    path("reports/distributions/", views.report_distributions, name="report_distributions"),
]
