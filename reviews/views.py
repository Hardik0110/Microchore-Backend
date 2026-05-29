import logging
from decimal import Decimal

from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Subquery
from django.utils import timezone

from .permissions import IsReviewer
from .models import Review, Bundle, ReviewerStats
from .serializers import ReviewCreateSerializer

from submissions.models import Submission
from submissions.serializers import SubmissionSerializer
from earnings.models import Earning
from accounts.models import User


logger = logging.getLogger(__name__)
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

        # BE-008: a worker must never review their own submission. The queue
        # already excludes own work, but the direct POST endpoint did not.
        if submission.claim.user_id == request.user.id:
            return Response(
                {'detail': 'You cannot review your own submission.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # BE-007: only PENDING/IN_REVIEW submissions are reviewable. The old
        # check let HELD (and any non-final) state through, so a 4th reviewer
        # could mint REVIEW_PAY against an already-escalated submission.
        if submission.status not in ('PENDING', 'IN_REVIEW'):
            return Response({'detail': 'Submission is no longer open for review.'}, status=status.HTTP_400_BAD_REQUEST)

        if Review.objects.filter(submission=submission, reviewer=request.user).exists():
            return Response({'detail': 'You have already reviewed this submission.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(submission=submission, reviewer=request.user)

        stats, _ = ReviewerStats.objects.select_for_update().get_or_create(user=request.user)
        today = timezone.now().date()
        is_same_day = bool(stats.last_review_at and stats.last_review_at.date() == today)
        now = timezone.now()
        if is_same_day:
            ReviewerStats.objects.filter(pk=stats.pk).update(
                daily_review_count=F('daily_review_count') + 1,
                reviews_completed=F('reviews_completed') + 1,
                last_review_at=now,
            )
        else:
            ReviewerStats.objects.filter(pk=stats.pk).update(
                daily_review_count=1,
                reviews_completed=F('reviews_completed') + 1,
                last_review_at=now,
            )

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
            # BE-015: consensus decided with integer-exact arithmetic only.
            # Ratings are integers (1..5), n = 3. Avoid binary float so the
            # money-affecting approve/hold boundary is deterministic.
            ratings = [r.rating for r in reviews]
            rating_sum = sum(ratings)
            sum_of_squares = sum(r * r for r in ratings)
            #   variance = (sum_of_squares - rating_sum**2 / n) / n,  n = 3
            #   variance <= 1.0  <=>  3 * sum_of_squares - rating_sum**2 <= 9
            low_dispersion = (3 * sum_of_squares - rating_sum * rating_sum) <= 9
            ai_flags = sum(1 for r in reviews if r.feels_ai_flag)

            project = submission.claim.task.project
            worker_id = submission.claim.user_id
            mean_decimal = (Decimal(rating_sum) / Decimal(3)).quantize(Decimal('0.01'))

            if low_dispersion and ai_flags < 2:
                # mean >= 3.0  <=>  rating_sum >= 9  (n = 3)
                is_approved = rating_sum >= 9
                submission.status = 'APPROVED' if is_approved else 'REJECTED'

                sorted_reviews = sorted(reviews, key=lambda r: r.rating)
                median_review = sorted_reviews[1]
                median_review.is_authoritative = True
                median_review.save(update_fields=['is_authoritative'])

                submission.justification = median_review.justification_text
                submission.rating_final = mean_decimal
                submission.reviewed_at = timezone.now()

                base_payout = (
                    project.pay_rate_per_approved_task
                    if is_approved and not project.is_starter
                    else Decimal('0.0000')
                )
                submission.base_payout = base_payout
                submission.save(update_fields=[
                    'status', 'justification', 'rating_final',
                    'reviewed_at', 'base_payout',
                ])

                if is_approved and base_payout > Decimal('0'):
                    # BE-004: a submission must never end APPROVED with a
                    # base_payout but no Earning row. Use a savepoint so the
                    # IntegrityError only rolls back the failed INSERT, then
                    # re-query: a genuine duplicate is idempotent (ignore), but
                    # any other failure re-raises and aborts the whole approval.
                    try:
                        with transaction.atomic():
                            Earning.objects.create(
                                user_id=worker_id,
                                project=project,
                                submission=submission,
                                amount=base_payout,
                                kind='BASE',
                                status='PENDING_PAYOUT',
                            )
                    except IntegrityError:
                        already_paid = Earning.objects.filter(
                            submission=submission, kind='BASE',
                        ).exists()
                        if not already_paid:
                            logger.error(
                                'BASE earning failed for submission=%s worker=%s; '
                                'rolling back approval to avoid unpaid APPROVED state.',
                                submission.pk, worker_id,
                            )
                            raise
                        logger.warning(
                            'Duplicate BASE earning suppressed for submission=%s worker=%s',
                            submission.pk, worker_id,
                        )

                if project.is_starter:
                    field = 'starter_approved' if is_approved else 'starter_rejected'
                    User.objects.filter(pk=worker_id).update(**{field: F(field) + 1})

            else:
                submission.status = 'HELD'
                submission.save(update_fields=['status'])

                admin_user = (
                    User.objects
                    .filter(reviewer_stats__tier='ADMIN', is_active=True)
                    .first()
                )
                if admin_user:
                    bundle, _ = Bundle.objects.get_or_create(
                        reviewer=admin_user,
                        status='OPEN',
                    )
                    bundle.submissions.add(submission)
                else:
                    # BE-023: no ADMIN reviewer to receive the escalation. The
                    # submission stays HELD (discoverable via status=HELD with
                    # no OPEN bundle). Logged at CRITICAL so ops alerting can
                    # page on it. NOTE: a proper AlertEvent sink is still
                    # required (BE-019) for guaranteed delivery.
                    logger.critical(
                        'Submission %s escalated to HELD but no ADMIN reviewer exists. '
                        'Manual intervention required — worker payout is blocked until resolved.',
                        submission.pk,
                    )

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
        'reviewCount': getattr(submission, 'review_count', submission.reviews.count()),
    }


class ReviewerQueueView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsReviewer]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit') or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 50))

        already_reviewed = Review.objects.filter(reviewer=request.user).values('submission_id')

        candidates = (
            Submission.objects
            .filter(status__in=['PENDING', 'IN_REVIEW'])
            .filter(claim__task__project__is_starter=False)
            .exclude(claim__user=request.user)
            .exclude(pk__in=Subquery(already_reviewed))
            .select_related('claim', 'claim__task', 'claim__task__project')
            .annotate(review_count=Count('reviews'))
            .order_by('submitted_at')[:limit]
        )

        return Response([_serialize_for_queue(s) for s in candidates])


class ReviewerStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsReviewer]

    def get(self, request):
        from django.db.models import Sum
        from earnings.models import Earning
        from datetime import timedelta

        stats = ReviewerStats.objects.filter(user=request.user).first()
        queue_size = (
            Submission.objects
            .filter(status__in=['PENDING', 'IN_REVIEW'])
            .filter(claim__task__project__is_starter=False)
            .exclude(claim__user=request.user)
            .exclude(pk__in=Subquery(Review.objects.filter(reviewer=request.user).values('submission_id')))
            .count()
        )

        earnings_qs = Earning.objects.filter(user=request.user, kind='REVIEW_PAY')
        totals = earnings_qs.aggregate(
            total_paid=Sum('amount', filter=models_q_status('PAID')),
            total_pending=Sum('amount', filter=models_q_status('PENDING_PAYOUT')),
        )

        seven_days_ago = timezone.now() - timedelta(days=7)
        recent_reviews = Review.objects.filter(reviewer=request.user, created_at__gte=seven_days_ago).count()

        recent_earnings = list(
            earnings_qs
            .select_related('submission', 'project')
            .order_by('-created_at')[:20]
        )

        return Response({
            'tier': stats.tier if stats else 'T1',
            'multiplier': float(stats.current_pay_multiplier) if stats and stats.current_pay_multiplier is not None else 1.0,
            'reviewsCompleted': stats.reviews_completed if stats else 0,
            'dailyReviewCount': stats.daily_review_count if stats else 0,
            'rollingAccuracyScore': float(stats.rolling_accuracy_score) if stats and stats.rolling_accuracy_score is not None else None,
            'lastReviewAt': stats.last_review_at.isoformat() if stats and stats.last_review_at else None,
            'queueSize': queue_size,
            'recentReviewsLast7Days': recent_reviews,
            'totalPaid': float(totals['total_paid'] or 0),
            'totalPending': float(totals['total_pending'] or 0),
            'recentEarnings': [
                {
                    'id': e.id,
                    'amount': float(e.amount),
                    'status': e.status,
                    'projectName': e.project.name if e.project_id else None,
                    'createdAt': e.created_at.isoformat() if e.created_at else None,
                    'paidAt': e.paid_at.isoformat() if e.paid_at else None,
                }
                for e in recent_earnings
            ],
        })


def models_q_status(status_value):
    from django.db.models import Q
    return Q(status=status_value)
