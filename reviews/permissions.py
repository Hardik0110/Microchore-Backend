from rest_framework import permissions

from .models import ReviewerStats


def user_is_reviewer(user) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    try:
        stats = user.reviewer_stats
    except ReviewerStats.DoesNotExist:
        return False
    return stats.tier in ('T1', 'T2', 'ADMIN')


class IsReviewer(permissions.BasePermission):
    """Allow access only to users with a ReviewerStats row in an active tier, or staff."""

    message = 'Reviewer access required.'

    def has_permission(self, request, view):
        return user_is_reviewer(getattr(request, 'user', None))
