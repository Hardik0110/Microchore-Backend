from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from reviews.permissions import user_is_reviewer
from projects.models import Task

REVIEWER_BLOCK_MSG = 'Reviewer accounts cannot claim or submit tasks.'
INACTIVE_ACCOUNT_MSG = 'Account is not active.'
ONBOARDING_MSG = 'Complete the starter run before claiming real tasks.'
PROJECT_CLOSED_MSG = 'This campaign is no longer accepting submissions.'
TASK_EXPIRED_MSG = 'Task has expired.'
CLAIM_CAP_MSG = 'You already have the maximum number of active claims.'

from .models import Claim, Submission
from .serializers import (
    ClaimSerializer,
    SubmissionCreateSerializer,
    SubmissionSerializer,
)


class MySubmissionListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]

    def get_throttles(self):
        if self.request.method == 'POST':
            self.throttle_scope = 'submission_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        return (
            Submission.objects
            .select_related('claim', 'claim__task', 'claim__task__project')
            .filter(claim__user=self.request.user)
            .order_by('-submitted_at')
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SubmissionCreateSerializer
        return SubmissionSerializer

    def create(self, request, *args, **kwargs):
        if user_is_reviewer(request.user):
            return Response({'detail': REVIEWER_BLOCK_MSG}, status=status.HTTP_403_FORBIDDEN)
        if getattr(request.user, 'status', None) != 'ACTIVE':
            return Response({'detail': INACTIVE_ACCOUNT_MSG}, status=status.HTTP_403_FORBIDDEN)
        serializer = SubmissionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        out = SubmissionSerializer(submission).data
        return Response(out, status=status.HTTP_201_CREATED)


class TaskClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        if user_is_reviewer(request.user):
            return Response({'detail': REVIEWER_BLOCK_MSG}, status=status.HTTP_403_FORBIDDEN)
        if getattr(request.user, 'status', None) != 'ACTIVE':
            return Response({'detail': INACTIVE_ACCOUNT_MSG}, status=status.HTTP_403_FORBIDDEN)
        try:
            task = Task.objects.select_for_update().select_related('project').get(pk=pk)
        except Task.DoesNotExist:
            return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        if getattr(task.project, 'status', None) != 'ACTIVE':
            return Response({'detail': PROJECT_CLOSED_MSG}, status=status.HTTP_400_BAD_REQUEST)
        if task.expires_at and task.expires_at <= timezone.now():
            return Response({'detail': TASK_EXPIRED_MSG}, status=status.HTTP_400_BAD_REQUEST)
        if not task.project.is_starter and not request.user.real_tasks_unlocked:
            return Response({'detail': ONBOARDING_MSG}, status=status.HTTP_403_FORBIDDEN)

        if task.status != 'OPEN' or task.remaining_count <= 0:
            return Response({'detail': 'Task is no longer available for claims.'}, status=status.HTTP_400_BAD_REQUEST)

        active_cap = getattr(settings, 'MICROCHORE_ACTIVE_CLAIM_CAP', 10)
        existing_active = Claim.objects.filter(
            user=request.user,
            status='ACTIVE',
            expires_at__gt=timezone.now(),
        ).exclude(task=task).count()
        if existing_active >= active_cap:
            return Response({'detail': CLAIM_CAP_MSG}, status=status.HTTP_400_BAD_REQUEST)

        already_submitted = Claim.objects.filter(
            task=task, user=request.user, status='SUBMITTED',
        ).exists()
        if already_submitted:
            return Response(
                {'detail': 'You have already submitted on this task.'},
                status=status.HTTP_409_CONFLICT,
            )

        existing_claim = Claim.objects.filter(task=task, user=request.user, status='ACTIVE').first()
        if existing_claim:
            if existing_claim.expires_at <= timezone.now():
                existing_claim.status = 'EXPIRED'
                existing_claim.save(update_fields=['status'])
            else:
                serializer = ClaimSerializer(existing_claim)
                return Response(serializer.data, status=status.HTTP_200_OK)

        task.remaining_count -= 1
        if task.remaining_count == 0:
            task.status = 'EXHAUSTED'
        task.save(update_fields=['remaining_count', 'status'])

        claim = Claim.objects.create(
            task=task,
            user=request.user,
            status='ACTIVE',
            expires_at=timezone.now() + timedelta(hours=24)
        )

        serializer = ClaimSerializer(claim)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

