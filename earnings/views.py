from decimal import Decimal

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from submissions.models import Submission
from submissions.serializers import SubmissionSerializer


class MyEarningsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = (
            Submission.objects
            .select_related('claim', 'claim__task', 'claim__task__project')
            .filter(claim__user=request.user, claim__task__project__is_starter=False)
            .order_by('-submitted_at')
        )
        rows = list(qs)
        approved = [s for s in rows if s.status == 'APPROVED']
        pending = [s for s in rows if s.status in ('PENDING', 'IN_REVIEW', 'HELD')]
        rejected = [s for s in rows if s.status == 'REJECTED']

        total_earned = sum(
            (s.base_payout or Decimal('0')) + (s.bonus_payout or Decimal('0')) for s in approved
        )
        if approved:
            ratings = [int(s.rating_final) for s in approved if s.rating_final is not None]
            avg_rating = (sum(ratings) / len(ratings)) if ratings else 0
        else:
            avg_rating = 0

        approved_payload = SubmissionSerializer(approved, many=True).data
        all_payload = SubmissionSerializer(rows, many=True).data

        return Response({
            'approvedCount': len(approved),
            'pendingCount': len(pending),
            'rejectedCount': len(rejected),
            'totalEarned': float(total_earned),
            'averageRating': avg_rating,
            'approved': approved_payload,
            'latest': approved_payload[0] if approved_payload else None,
            'all': all_payload,
        })
