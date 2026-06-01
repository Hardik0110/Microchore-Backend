import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from ai_detection.service import (
    AIDetectionUnavailable,
    evaluate_for_project,
    is_configured as ai_detection_is_configured,
)
from projects.models import Task

from .models import Claim, Submission


logger = logging.getLogger(__name__)


STATUS_TO_FRONTEND = {
    'PENDING': 'pending',
    'IN_REVIEW': 'pending',
    'HELD': 'pending',
    'APPROVED': 'approved',
    'REJECTED': 'rejected',
}


class ClaimSerializer(serializers.ModelSerializer):
    taskId = serializers.IntegerField(source='task.id', read_only=True)
    userId = serializers.IntegerField(source='user.id', read_only=True)
    claimedAt = serializers.DateTimeField(source='claimed_at', read_only=True)
    expiresAt = serializers.DateTimeField(source='expires_at', read_only=True)

    class Meta:
        model = Claim
        fields = ['id', 'taskId', 'userId', 'claimedAt', 'expiresAt', 'status']


class SubmissionSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    taskId = serializers.SerializerMethodField()
    taskTitle = serializers.SerializerMethodField()
    taskTone = serializers.SerializerMethodField()
    text = serializers.CharField(source='comment_text_snapshot')
    commentUrl = serializers.URLField(source='comment_url')
    pasteCount = serializers.IntegerField(source='paste_event_count')
    charsTyped = serializers.IntegerField(source='keypress_count')
    pastedChars = serializers.IntegerField(source='pasted_chars')
    elapsedSec = serializers.IntegerField(source='time_to_compose_seconds')
    attestationSigned = serializers.BooleanField(source='attestation_signed')
    status = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    justification = serializers.CharField(allow_blank=True, required=False)
    basePayout = serializers.DecimalField(source='base_payout', max_digits=10, decimal_places=4, coerce_to_string=False)
    bonusPayout = serializers.DecimalField(source='bonus_payout', max_digits=10, decimal_places=4, coerce_to_string=False)
    submittedAt = serializers.DateTimeField(source='submitted_at', read_only=True)
    reviewedAt = serializers.DateTimeField(source='reviewed_at', allow_null=True, required=False)
    isStarter = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            'id', 'taskId', 'taskTitle', 'taskTone',
            'text', 'commentUrl', 'pasteCount', 'charsTyped', 'pastedChars',
            'elapsedSec', 'attestationSigned',
            'status', 'rating', 'justification',
            'basePayout', 'bonusPayout',
            'submittedAt', 'reviewedAt', 'isStarter',
        ]

    def get_id(self, obj):
        return str(obj.pk)

    def get_taskId(self, obj):
        return str(obj.claim.task_id)

    def get_taskTitle(self, obj):
        return obj.claim.task.project.name

    def get_taskTone(self, obj):
        return obj.claim.task.project.tone

    def get_status(self, obj):
        return STATUS_TO_FRONTEND.get(obj.status, 'pending')

    def get_rating(self, obj):
        if obj.rating_final is None:
            return None
        return int(Decimal(obj.rating_final).to_integral_value(rounding='ROUND_HALF_UP'))

    def get_isStarter(self, obj):
        return bool(obj.claim.task.project.is_starter)


class SubmissionCreateSerializer(serializers.Serializer):
    taskId = serializers.IntegerField()
    text = serializers.CharField()
    commentUrl = serializers.URLField()
    pasteCount = serializers.IntegerField(default=0, min_value=0, max_value=10_000)
    charsTyped = serializers.IntegerField(default=0, min_value=0, max_value=1_000_000)
    pastedChars = serializers.IntegerField(default=0, min_value=0, max_value=1_000_000)
    elapsedSec = serializers.IntegerField(default=0, min_value=0, max_value=86_400)
    attestationSigned = serializers.BooleanField(default=False)
    socialAccountId = serializers.IntegerField(required=False, allow_null=True)

    def _verify_social_account(self, user, comment_url, social_account_id):
        from accounts.models import SocialAccount
        from urllib.parse import urlparse

        def _platform_from_url(url):
            try:
                host = (urlparse(url).hostname or '').lower()
            except Exception:
                return None
            if 'youtube.com' in host or 'youtu.be' in host:
                return 'YT'
            if 'instagram.com' in host:
                return 'IG'
            if 'tiktok.com' in host:
                return 'TIKTOK'
            if 'twitter.com' in host or host == 'x.com' or host.endswith('.x.com'):
                return 'X'
            return None

        platform = _platform_from_url(comment_url)
        if not platform:
            return None
        qs = SocialAccount.objects.filter(user=user, platform=platform, is_active=True, verified_at__isnull=False)
        if social_account_id:
            qs = qs.filter(pk=social_account_id)
        account = qs.first()
        if not account:
            raise serializers.ValidationError({
                'commentUrl': 'A verified social account matching this platform is required.',
            })
        return account

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        text = validated_data['text']
        comment_url = validated_data['commentUrl']

        with transaction.atomic():
            try:
                task = (
                    Task.objects.select_for_update()
                    .select_related('project')
                    .get(pk=validated_data['taskId'])
                )
            except Task.DoesNotExist:
                raise serializers.ValidationError({'taskId': 'Task does not exist'})

            project = task.project
            if getattr(project, 'status', None) != 'ACTIVE':
                raise serializers.ValidationError({'taskId': 'This campaign is no longer accepting submissions.'})
            if task.expires_at and task.expires_at <= timezone.now():
                raise serializers.ValidationError({'taskId': 'Task has expired.'})
            if not project.is_starter and not user.real_tasks_unlocked:
                raise serializers.ValidationError({'taskId': 'Complete the starter run before submitting real tasks.'})

            if Submission.objects.filter(claim__user=user, claim__task=task).exists():
                raise serializers.ValidationError({
                    'taskId': 'You have already submitted on this task.',
                })

            social_account = None
            if not project.is_starter:
                social_account = self._verify_social_account(
                    user, comment_url, validated_data.get('socialAccountId'),
                )
                if social_account and social_account.platform == 'YT':
                    from verification.youtube_comment import verify_comment, extract_video_id
                    target_video_id = extract_video_id(
                        task.target_post_url or project.target_post_url_default or ''
                    )
                    result = verify_comment(
                        comment_url=comment_url,
                        expected_channel_id=social_account.external_id or '',
                        expected_video_id=target_video_id,
                    )
                    if not result.ok:
                        raise serializers.ValidationError({'commentUrl': result.error_message})
                if social_account and social_account.platform == 'IG':
                    from verification.instagram import verify_comment as verify_ig_comment
                    ig_result = verify_ig_comment(
                        comment_url=comment_url,
                        expected_handle=social_account.handle or '',
                        expected_text=text,
                    )
                    if not ig_result.ok:
                        raise serializers.ValidationError({'commentUrl': ig_result.error_message})

            if project.is_starter:
                if task.status != 'OPEN' or task.remaining_count <= 0:
                    raise serializers.ValidationError({'taskId': 'Task is no longer available.'})
                claim, created = Claim.objects.get_or_create(
                    task=task,
                    user=user,
                    status='ACTIVE',
                    defaults={'expires_at': timezone.now() + timedelta(hours=24)},
                )
                if created:
                    task.remaining_count = F('remaining_count') - 1
                    task.save(update_fields=['remaining_count'])
                    task.refresh_from_db(fields=['remaining_count'])
                    if task.remaining_count <= 0:
                        Task.objects.filter(pk=task.pk).update(status='EXHAUSTED')
            else:
                claim = Claim.objects.filter(task=task, user=user, status='ACTIVE').first()
                if not claim:
                    raise serializers.ValidationError({'taskId': 'You must claim this task before making a submission.'})
                if claim.expires_at <= timezone.now():
                    claim.status = 'EXPIRED'
                    claim.save(update_fields=['status'])
                    raise serializers.ValidationError({'taskId': 'Your claim on this task has expired.'})

            claim.status = 'SUBMITTED'
            claim.save(update_fields=['status'])

            stored_handle = (
                social_account.handle if social_account else (user.handle or (user.email.split('@')[0] if user.email else ''))
            )
            stored_handle = (stored_handle or '')[:100]

            submission = Submission.objects.create(
                claim=claim,
                comment_url=comment_url,
                comment_text_snapshot=text,
                comment_account_handle=stored_handle,
                proof_type='URL',
                paste_event_count=validated_data['pasteCount'],
                pasted_chars=validated_data['pastedChars'],
                keypress_count=validated_data['charsTyped'],
                time_to_compose_seconds=validated_data['elapsedSec'],
                attestation_signed=validated_data['attestationSigned'],
                ai_likelihood_score=Decimal('0.0'),
                status='PENDING',
            )

        ai_score = Decimal('0.0')
        new_status = 'PENDING'
        project = submission.claim.task.project
        if ai_detection_is_configured():
            try:
                result = evaluate_for_project(text, project.ai_detection_strictness)
                if result is not None:
                    ai_score = result.score
                    if result.flagged:
                        new_status = 'HELD'
            except AIDetectionUnavailable as exc:
                logger.error(
                    'AI detection unavailable for submission by user=%s on task=%s: %s',
                    user.id, submission.claim.task_id, exc,
                )
                new_status = 'HELD'
        elif not project.is_starter:
            logger.warning('AI detection not configured; submitting without score.')

        if ai_score != Decimal('0.0') or new_status != 'PENDING':
            with transaction.atomic():
                Submission.objects.filter(pk=submission.pk).update(
                    ai_likelihood_score=ai_score,
                    status=new_status,
                )
            submission.refresh_from_db(fields=['ai_likelihood_score', 'status'])

        return submission


