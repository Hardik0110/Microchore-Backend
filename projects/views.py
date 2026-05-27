from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCompanyAdmin
from reviews.permissions import user_is_reviewer

from .models import Project, Task
from .serializers import (
    ProjectCreateSerializer,
    ProjectSerializer,
    ProjectStatusUpdateSerializer,
    ProjectTaskCreateSerializer,
    TaskListSerializer,
)


class TaskListView(generics.ListAPIView):
    serializer_class = TaskListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if user_is_reviewer(self.request.user):
            return Task.objects.none()
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


class ProjectListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsCompanyAdmin()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        projects = (
            Project.objects.select_related('company')
            .filter(is_starter=False)
            .order_by('-created_at')
        )
        return Response(ProjectSerializer(projects, many=True).data)

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ProjectDetailUpdateView(APIView):
    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [permissions.IsAuthenticated(), IsCompanyAdmin()]
        return [permissions.IsAuthenticated()]

    def _get(self, pk):
        try:
            return Project.objects.select_related('company').get(pk=pk)
        except Project.DoesNotExist:
            return None

    def get(self, request, pk):
        project = self._get(pk)
        if project is None:
            return Response({'detail': 'Project not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProjectSerializer(project).data)

    def patch(self, request, pk):
        project = self._get(pk)
        if project is None:
            return Response({'detail': 'Project not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProjectStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.update(project, serializer.validated_data)
        return Response(ProjectSerializer(project).data)


class ProjectTaskCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCompanyAdmin]

    def post(self, request, pk):
        try:
            project = Project.objects.select_related('company').get(pk=pk)
        except Project.DoesNotExist:
            return Response({'detail': 'Project not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProjectTaskCreateSerializer(data=request.data, context={'project': project})
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        return Response(TaskListSerializer(task).data, status=status.HTTP_201_CREATED)
