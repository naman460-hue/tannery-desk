from rest_framework.permissions import BasePermission


class RolePermission(BasePermission):
    roles = ()
    message = "You do not have permission to do that."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.role in self.roles)


class IsClient(RolePermission):
    roles = ("CLIENT",)


class IsFactory(RolePermission):
    roles = ("FACTORY",)


class IsAdminRole(RolePermission):
    roles = ("ADMIN",)


class IsVerifiedFactory(BasePermission):
    message = "Your factory has not been verified yet. You can use this once the Tannery Desk team approves your profile."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.role == "FACTORY"):
            return False
        profile = getattr(user, "factory_profile", None)
        return bool(profile and profile.verification_status == "VERIFIED")
