from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """
    Phase 1 post-login landing view.
    Renders user identity, role, and associated organization.
    """
    return render(request, 'home.html', {
        'user': request.user,
    })
