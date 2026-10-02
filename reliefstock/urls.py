"""
URL configuration for reliefstock project.

Phase 1 Routes:
- /admin/            : Django Administration Interface
- /accounts/login/   : Built-in Authentication Login View
- /accounts/logout/  : Built-in Authentication Logout View
- /                  : Authenticated user dashboard / placeholder landing page
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from accounts.views import home

urlpatterns = [
    # Admin Interface
    path('admin/', admin.site.urls),

    # Built-in Auth Views
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login'
    ),
    path(
        'accounts/logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),

    # Application Landing / Dashboard
    path('', home, name='home'),
]
