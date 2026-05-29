from rest_framework import permissions


COMPANY_ROLES = ('COMPANY_ADMIN', 'PLATFORM_ADMIN')


def user_is_company_admin(user) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_staff', False):
        return True
    return getattr(user, 'role', None) in COMPANY_ROLES


def user_is_platform_admin(user) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) == 'PLATFORM_ADMIN'


class IsCompanyAdmin(permissions.BasePermission):
    message = 'Company admin access required.'

    def has_permission(self, request, view):
        return user_is_company_admin(getattr(request, 'user', None))


class IsPlatformAdmin(permissions.BasePermission):
    message = 'Platform admin access required.'

    def has_permission(self, request, view):
        return user_is_platform_admin(getattr(request, 'user', None))


class IsActiveAccount(permissions.BasePermission):
    message = 'Account is not active.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'status', None) == 'ACTIVE'
