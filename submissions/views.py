from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from reviews.permissions import IsReviewer, user_is_reviewer
from projects.models import Task

REVIEWER_BLOCK_MSG = 'Reviewer accounts cannot claim or submit tasks.'

from .models import Claim, Submission
from .serializers import (
    ClaimSerializer,
    SubmissionCreateSerializer,
    SubmissionReviewSerializer,
    SubmissionSerializer,
)


class MySubmissionListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

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
        serializer = SubmissionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        out = SubmissionSerializer(submission).data
        return Response(out, status=status.HTTP_201_CREATED)


class SubmissionReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsReviewer]

    def post(self, request, pk):
        try:
            submission = (
                Submission.objects
                .select_related('claim', 'claim__task', 'claim__task__project', 'claim__user')
                .get(pk=pk)
            )
        except Submission.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if submission.claim.user_id == request.user.id:
            return Response(
                {'detail': 'You cannot review your own submission.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SubmissionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = serializer.apply(submission)
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)


class TaskClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        if user_is_reviewer(request.user):
            return Response({'detail': REVIEWER_BLOCK_MSG}, status=status.HTTP_403_FORBIDDEN)
        try:
            task = Task.objects.select_for_update().get(pk=pk)
        except Task.DoesNotExist:
            return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        if task.status != 'OPEN' or task.remaining_count <= 0:
            return Response({'detail': 'Task is no longer available for claims.'}, status=status.HTTP_400_BAD_REQUEST)

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

