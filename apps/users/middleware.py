from django.shortcuts import redirect
from django.contrib import messages
from apps.users.models import User


class AdminAccessRestrictionMiddleware:
    """
    Ensures /admin/ can only be visited by Superusers or Admins.
    If visited by any other user (such as a Member), they are redirected
    to the Member Dashboard (/).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            # Allow logout to proceed
            if request.path.startswith('/admin/logout/'):
                return self.get_response(request)

            if request.user.is_authenticated:
                is_admin = (
                    request.user.is_superuser
                    or getattr(request.user, 'role', None) in [User.Role.SUPERUSER, User.Role.ADMIN]
                    or getattr(request.user, 'is_staff', False)
                )
                if not is_admin:
                    messages.warning(
                        request,
                        "Access restricted: The admin console is for Superusers and Admins only. You have been redirected to the Member Dashboard."
                    )
                    return redirect('/')

        return self.get_response(request)

