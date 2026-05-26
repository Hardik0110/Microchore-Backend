from rest_framework import permissions

from .models import ReviewerStats


class IsReviewer(permissions.BasePermission):
    """Allow access only to users with a ReviewerStats row in an active tier, or staff."""

    message = 'Reviewer access required.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        try:
            stats = user.reviewer_stats
        except ReviewerStats.DoesNotExist:
            return False
        return stats.tier in ('T1', 'T2', 'ADMIN')
