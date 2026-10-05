from rest_framework import permissions


class IsStaffOrAdmin(permissions.BasePermission):
    """
    Allows access only to authenticated STAFF or ADMIN users affiliated with an Organization.
    Superusers bypass role restrictions.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role in ["STAFF", "ADMIN"] and user.organization is not None


class IsVolunteerOrStaff(permissions.BasePermission):
    """
    Allows access to VOLUNTEER, STAFF, or ADMIN users affiliated with an Organization.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role in ["VOLUNTEER", "STAFF", "ADMIN"] and user.organization is not None


class IsAdminOnly(permissions.BasePermission):
    """
    Allows access only to ADMIN users affiliated with an Organization (or superusers).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role == "ADMIN" and user.organization is not None


class IsDonorOnly(permissions.BasePermission):
    """
    Allows access only to DONOR users.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role == "DONOR"


class IsStaffOrAdminOrDonorReadOnly(permissions.BasePermission):
    """
    Staff and Admins have full access.
    Donors have read-only access to their personal objects.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.role in ["STAFF", "ADMIN", "VOLUNTEER"]:
            return True
        if user.role == "DONOR" and request.method in permissions.SAFE_METHODS:
            return True
        return False
