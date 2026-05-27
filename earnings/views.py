from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from submissions.models import Submission
from submissions.serializers import SubmissionSerializer


MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


class MyEarningsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit') or DEFAULT_PAGE_SIZE)
        except (TypeError, ValueError):
            limit = DEFAULT_PAGE_SIZE
        limit = max(1, min(limit, MAX_PAGE_SIZE))

        base_qs = (
            Submission.objects
            .select_related('claim', 'claim__task', 'claim__task__project')
            .filter(claim__user=request.user, claim__task__project__is_starter=False)
        )

        approved_qs = base_qs.filter(status='APPROVED')
        agg = base_qs.aggregate(
            approved_count=Count('pk', filter=Q(status='APPROVED')),
            pending_count=Count('pk', filter=Q(status__in=['PENDING', 'IN_REVIEW', 'HELD'])),
            rejected_count=Count('pk', filter=Q(status='REJECTED')),
            total_earned=Coalesce(
                Sum(F('base_payout') + F('bonus_payout'), filter=Q(status='APPROVED')),
                Decimal('0'),
                output_field=DecimalField(max_digits=12, decimal_places=4),
            ),
        )

        ratings = list(
            approved_qs.exclude(rating_final__isnull=True).values_list('rating_final', flat=True)
        )
        avg_rating = (sum(int(r) for r in ratings) / len(ratings)) if ratings else 0

        approved_rows = list(approved_qs.order_by('-submitted_at')[:limit])
        latest_rows = list(base_qs.order_by('-submitted_at')[:limit])
        approved_payload = SubmissionSerializer(approved_rows, many=True).data
        all_payload = SubmissionSerializer(latest_rows, many=True).data

        return Response({
            'approvedCount': agg['approved_count'],
            'pendingCount': agg['pending_count'],
            'rejectedCount': agg['rejected_count'],
            'totalEarned': float(agg['total_earned']),
            'averageRating': avg_rating,
            'approved': approved_payload,
            'latest': approved_payload[0] if approved_payload else None,
            'all': all_payload,
            'limit': limit,
        })
