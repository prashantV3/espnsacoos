from rest_framework import permissions


class IsSuperUser(permissions.BasePermission):
    """
    Grants access only to Superusers.
    Superusers can configure global settings, create users, assign roles, and define base interest rates.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.role == 'SUPERUSER' or request.user.is_superuser)
        )


class IsAdminOrSuperUser(permissions.BasePermission):
    """
    Grants access to Financial Operators (Admins) and Superusers.
    Admins can enter transactions, grant emergency advances, and define grace periods.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (
                request.user.role in ['ADMIN', 'SUPERUSER'] or
                request.user.is_staff or
                request.user.is_superuser
            )
        )


class IsMember(permissions.BasePermission):
    """
    Checks if user is authenticated and has Member role.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'MEMBER'
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level permission allowing members to view their own records,
    while Admins and Superusers have view/manage access.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role in ['ADMIN', 'SUPERUSER'] or request.user.is_staff:
            return True

        # Check if object has user or borrower attribute
        target_user = getattr(obj, 'user', None) or getattr(obj, 'borrower', None)
        return target_user == request.user

