from rest_framework import permissions

class IsCompanyUser(permissions.BasePermission):
    """
    Custom permission to only allow users associated with a company to access their company's data.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'hr_profile')) 