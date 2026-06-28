from rest_framework import permissions

class IsSelf(permissions.BasePermission):
    """
    Custom permission to only allow users to view or edit their own user object.
    """
    def has_object_permission(self, request, view, obj):
        # Read-only or write operations are only allowed if the object is the request user
        return obj == request.user
