from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Prefetch, Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from reviews.models import ReviewerStats

from .models import SocialAccount
from .permissions import IsPlatformAdmin


User = get_user_model()


MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
ALLOWED_TIERS = ('T1', 'T2', 'ADMIN')


def _serialize_user(user) -> dict:
    socials = []
    for sa in user.social_accounts.all():
        if not sa.is_active:
            continue
        socials.append({
            'platform': sa.platform,
            'handle': sa.handle,
            'followerCount': sa.follower_count,
            'postCount': sa.post_count,
            'accountAgeDays': sa.account_age_days,
            'verifiedAt': sa.verified_at.isoformat() if sa.verified_at else None,
        })
    reviewer_stats = getattr(user, 'reviewer_stats', None)
    avg_rating = getattr(user, 'avg_rating', None)
    approved_count = getattr(user, 'approved_submission_count', 0)
    submission_count = getattr(user, 'submission_count', 0)
    return {
        'id': user.id,
        'email': user.email,
        'handle': user.handle,
        'role': user.role,
        'status': user.status,
        'country': user.country,
        'emailVerified': user.email_verified,
        'wizardStep': user.wizard_step,
        'starterApproved': user.starter_approved,
        'starterRejected': user.starter_rejected,
        'createdAt': user.date_joined.isoformat() if user.date_joined else None,
        'socialAccounts': socials,
        'averageRating': float(avg_rating) if avg_rating is not None else None,
        'approvedSubmissionCount': approved_count,
        'submissionCount': submission_count,
        'reviewerTier': reviewer_stats.tier if reviewer_stats else None,
        'reviewerMultiplier': (
            float(reviewer_stats.current_pay_multiplier)
            if reviewer_stats and reviewer_stats.current_pay_multiplier is not None
            else None
        ),
        'reviewsCompleted': reviewer_stats.reviews_completed if reviewer_stats else 0,
        'rollingAccuracyScore': (
            float(reviewer_stats.rolling_accuracy_score)
            if reviewer_stats and reviewer_stats.rolling_accuracy_score is not None
            else None
        ),
    }


def _annotated_user_qs():
    return (
        User.objects
        .select_related('reviewer_stats')
        .prefetch_related(
            Prefetch(
                'social_accounts',
                queryset=SocialAccount.objects.filter(is_active=True),
            ),
        )
        .annotate(
            avg_rating=Avg(
                'claims__submission__rating_final',
                filter=Q(claims__submission__status='APPROVED'),
            ),
            approved_submission_count=Count(
                'claims__submission',
                filter=Q(claims__submission__status='APPROVED'),
                distinct=True,
            ),
            submission_count=Count('claims__submission', distinct=True),
        )
    )


class AdminUserListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit') or DEFAULT_PAGE_SIZE)
        except (TypeError, ValueError):
            limit = DEFAULT_PAGE_SIZE
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        try:
            offset = int(request.query_params.get('offset') or 0)
        except (TypeError, ValueError):
            offset = 0
        offset = max(0, offset)

        search = (request.query_params.get('q') or '').strip()
        role_filter = (request.query_params.get('role') or '').strip().upper()

        qs = _annotated_user_qs().order_by('-date_joined')
        if search:
            qs = qs.filter(Q(email__icontains=search) | Q(handle__icontains=search))
        if role_filter:
            qs = qs.filter(role=role_filter)

        total = qs.count()
        rows = list(qs[offset:offset + limit])
        return Response({
            'results': [_serialize_user(u) for u in rows],
            'limit': limit,
            'offset': offset,
            'total': total,
        })


class AdminPromoteReviewerView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        body = request.data if isinstance(request.data, dict) else {}
        tier = (body.get('tier') or 'T1').upper()
        if tier not in ALLOWED_TIERS:
            return Response(
                {'detail': f'Tier must be one of {ALLOWED_TIERS}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_multiplier = body.get('multiplier')
        if raw_multiplier is None:
            multiplier = Decimal('1.0')
        else:
            try:
                multiplier = Decimal(str(raw_multiplier))
            except (InvalidOperation, TypeError, ValueError):
                return Response(
                    {'detail': 'Multiplier must be a number.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if multiplier <= 0 or multiplier > 5:
                return Response(
                    {'detail': 'Multiplier must be between 0 and 5.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if user.role != 'REVIEWER':
            user.role = 'REVIEWER'
            user.save(update_fields=['role'])

        ReviewerStats.objects.update_or_create(
            user=user,
            defaults={'tier': tier, 'current_pay_multiplier': multiplier},
        )

        fresh = _annotated_user_qs().get(pk=user.pk)
        return Response(_serialize_user(fresh))
