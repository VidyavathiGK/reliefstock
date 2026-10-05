from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    DashboardAPIView,
    DistributionRequestViewSet,
    DonationViewSet,
    InventoryItemViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="api-category")
router.register("items", InventoryItemViewSet, basename="api-item")
router.register("donations", DonationViewSet, basename="api-donation")
router.register(
    "distribution-requests", DistributionRequestViewSet, basename="api-distribution-request"
)

urlpatterns = [
    # Router endpoints
    path("", include(router.urls)),
    # Executive dashboard summary endpoint
    path("dashboard/", DashboardAPIView.as_view(), name="api-dashboard"),
    # Token Authentication Endpoint
    path("auth/token/", obtain_auth_token, name="api-token-auth"),
]
