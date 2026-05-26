from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions

from .models import Task
from .serializers import TaskListSerializer


class TaskListView(generics.ListAPIView):
    serializer_class = TaskListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        now = timezone.now()
        return (
            Task.objects.select_related('project')
            .filter(status='OPEN', project__status='ACTIVE')
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .exclude(
                claims__user=self.request.user,
                claims__status__in=['ACTIVE', 'SUBMITTED'],
            )
            .order_by('-project__is_starter', '-created_at')
            .distinct()
        )


class TaskDetailView(generics.RetrieveAPIView):
    serializer_class = TaskListSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Task.objects.select_related('project').all()
