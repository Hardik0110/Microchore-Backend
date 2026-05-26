from decimal import Decimal

from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.utils import timezone

from .permissions import IsReviewer
from .models import Review, Bundle, ReviewerStats
from .serializers import ReviewCreateSerializer

from submissions.models import Submission
from submissions.serializers import SubmissionSerializer
from earnings.models import Earning
from accounts.models import User


REVIEW_PAY_PER_REVIEW = Decimal('0.05')


class ReviewCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsReviewer]

    @transaction.atomic
    def post(self, request, submission_id):
        try:
            submission = (
                Submission.objects
                .select_related('claim', 'claim__task', 'claim__task__project', 'claim__user')
                .select_for_update()
                .get(pk=submission_id)
            )
        except Submission.DoesNotExist:
            return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)

        if submission.status in ('APPROVED', 'REJECTED'):
            return Response({'detail': 'Submission is already fully reviewed.'}, status=status.HTTP_400_BAD_REQUEST)

        if Review.objects.filter(submission=submission, reviewer=request.user).exists():
            return Response({'detail': 'You have already reviewed this submission.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(submission=submission, reviewer=request.user)

        stats, _ = ReviewerStats.objects.get_or_create(user=request.user)
        today = timezone.now().date()
        if stats.last_review_at and stats.last_review_at.date() == today:
            stats.daily_review_count += 1
        else:
            stats.daily_review_count = 1
        stats.reviews_completed += 1
        stats.last_review_at = timezone.now()
        stats.save(update_fields=['daily_review_count', 'reviews_completed', 'last_review_at'])

        multiplier = stats.current_pay_multiplier or Decimal('1.0')
        Earning.objects.create(
            user=request.user,
            project=submission.claim.task.project,
            submission=submission,
            amount=REVIEW_PAY_PER_REVIEW * multiplier,
            kind='REVIEW_PAY',
            status='PENDING_PAYOUT',
        )

        if submission.status == 'PENDING':
            submission.status = 'IN_REVIEW'
            submission.save(update_fields=['status'])

        reviews = list(submission.reviews.all())
        count = len(reviews)

        if count == 3:
            ratings = [r.rating for r in reviews]
            mean = sum(ratings) / 3.0
            variance = sum((r - mean) ** 2 for r in ratings) / 3.0
            stdev = variance ** 0.5
            ai_flags = sum(1 for r in reviews if r.feels_ai_flag)

            project = submission.claim.task.project
            user = submission.claim.user

            if stdev <= 1.0 and ai_flags < 2:
                is_approved = mean >= 3.0
                submission.status = 'APPROVED' if is_approved else 'REJECTED'

                sorted_reviews = sorted(reviews, key=lambda r: r.rating)
                median_review = sorted_reviews[1]
                median_review.is_authoritative = True
                median_review.save(update_fields=['is_authoritative'])

                submission.justification = median_review.justification_text
                submission.rating_final = mean
                submission.reviewed_at = timezone.now()

                base_payout = project.pay_rate_per_approved_task if is_approved and not project.is_starter else 0
                submission.base_payout = base_payout
                submission.save()

                if is_approved and base_payout > 0:
                    Earning.objects.create(
                        user=user,
                        project=project,
                        submission=submission,
                        amount=base_payout,
                        kind='BASE',
                        status='PENDING_PAYOUT'
                    )

                if project.is_starter:
                    if is_approved:
                        user.starter_approved += 1
                    else:
                        user.starter_rejected += 1
                    user.save(update_fields=['starter_approved', 'starter_rejected'])

            else:
                submission.status = 'HELD'
                submission.save(update_fields=['status'])

                admin_user = User.objects.filter(reviewer_stats__tier='ADMIN', is_active=True).first()
                if admin_user:
                    bundle, _ = Bundle.objects.get_or_create(
                        reviewer=admin_user,
                        status='OPEN'
                    )
                    bundle.submissions.add(submission)

        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


def _serialize_for_queue(submission):
    task = submission.claim.task
    project = task.project
    return {
        'id': str(submission.pk),
        'taskId': str(task.pk),
        'taskTitle': project.name,
        'taskTone': project.tone,
        'targetUrl': task.target_post_url or project.target_post_url_default or '',
        'keyword': task.keyword or project.keyword_default or '',
        'text': submission.comment_text_snapshot,
        'commentUrl': submission.comment_url,
        'commentAccountHandle': submission.comment_account_handle,
        'elapsedSec': submission.time_to_compose_seconds,
        'pasteCount': submission.paste_event_count,
        'pastedChars': submission.pasted_chars,
        'charsTyped': submission.keypress_count,
        'submittedAt': submission.submitted_at.isoformat(),
        'reviewCount': submission.reviews.count(),
    }


class ReviewerQueueView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsReviewer]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit') or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 50))

        already_reviewed_ids = Review.objects.filter(
            reviewer=request.user
        ).values_list('submission_id', flat=True)

        candidates = (
            Submission.objects
            .filter(status__in=['PENDING', 'IN_REVIEW'])
            .filter(claim__task__project__is_starter=False)
            .exclude(claim__user=request.user)
            .exclude(pk__in=already_reviewed_ids)
            .select_related('claim', 'claim__task', 'claim__task__project')
            .order_by('submitted_at')[:limit]
        )

        return Response([_serialize_for_queue(s) for s in candidates])
