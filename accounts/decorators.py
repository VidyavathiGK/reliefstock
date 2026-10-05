from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect


def role_required(allowed_roles, require_organization=True, redirect_url="home"):
    """
    Decorator to restrict view access to specific user roles with multi-tenant org validation.

    1. Enforces authentication (@login_required).
    2. Enforces role authorization (allowed_roles). Superusers always bypass role checks.
    3. If require_organization=True, ensures user is affiliated with an active Organization,
       attaching `request.org = user.organization` for clean multi-tenant view queries.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user

            # 1. Superuser bypass
            if user.is_superuser:
                request.org = getattr(user, "organization", None)
                # If superuser has no org, fallback to first org if available so views work cleanly
                if require_organization and not request.org:
                    from organizations.models import Organization

                    request.org = Organization.objects.first()
                return view_func(request, *args, **kwargs)

            # 2. Role permission check
            user_role = getattr(user, "role", None)
            if user_role not in allowed_roles:
                role_display = (
                    user.get_role_display() if hasattr(user, "get_role_display") else "Current user"
                )
                messages.error(
                    request,
                    f"Permission denied: {role_display}s are not authorized to access that page.",
                )
                return redirect(redirect_url)

            # 3. Organization multi-tenancy verification
            if require_organization:
                user_org = getattr(user, "organization", None)
                if not user_org:
                    messages.warning(
                        request, "Your user profile is not linked to any organization."
                    )
                    return redirect("home")
                request.org = user_org

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def staff_or_admin_required(view_func=None, require_organization=True):
    """Decorator allowing only STAFF or ADMIN users with verified organization."""
    actual_decorator = role_required(["STAFF", "ADMIN"], require_organization=require_organization)
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


def volunteer_or_staff_required(view_func=None, require_organization=True):
    """Decorator allowing VOLUNTEER, STAFF, or ADMIN users with verified organization."""
    actual_decorator = role_required(
        ["VOLUNTEER", "STAFF", "ADMIN"], require_organization=require_organization
    )
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


def admin_required(view_func=None, require_organization=True):
    """Decorator allowing only ADMIN users (and superusers) with verified organization."""
    actual_decorator = role_required(["ADMIN"], require_organization=require_organization)
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


def donor_required(view_func=None):
    """Decorator allowing only DONOR users (does not require staff organization)."""
    actual_decorator = role_required(["DONOR"], require_organization=False)
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


class RoleRequiredMixin(AccessMixin):
    """
    Class-Based View mixin equivalent of role_required decorator.
    """

    allowed_roles = []
    require_organization = True
    redirect_url = "home"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        user = request.user
        if not user.is_superuser:
            if getattr(user, "role", None) not in self.allowed_roles:
                messages.error(
                    request,
                    f"Permission denied: {user.get_role_display()}s are not authorized to access that page.",
                )
                return redirect(self.redirect_url)

            if self.require_organization and not getattr(user, "organization", None):
                messages.warning(request, "Your user profile is not linked to any organization.")
                return redirect("home")

        request.org = getattr(user, "organization", None)
        return super().dispatch(request, *args, **kwargs)
