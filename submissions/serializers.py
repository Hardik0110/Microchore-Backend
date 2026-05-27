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
        return int(obj.rating_final)

    def get_isStarter(self, obj):
        return bool(obj.claim.task.project.is_starter)


class SubmissionCreateSerializer(serializers.Serializer):
    taskId = serializers.IntegerField()
    text = serializers.CharField()
    commentUrl = serializers.URLField()
    pasteCount = serializers.IntegerField(default=0)
    charsTyped = serializers.IntegerField(default=0)
    pastedChars = serializers.IntegerField(default=0)
    elapsedSec = serializers.IntegerField(default=0)
    attestationSigned = serializers.BooleanField(default=False)

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        try:
            task = Task.objects.select_for_update().select_related('project').get(pk=validated_data['taskId'])
        except Task.DoesNotExist:
            raise serializers.ValidationError({'taskId': 'Task does not exist'})

        if Submission.objects.filter(claim__user=user, claim__task=task).exists():
            raise serializers.ValidationError({
                'taskId': 'You have already submitted on this task.',
            })

        if task.project.is_starter:
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

        ai_score = Decimal('0.0')
        initial_status = 'PENDING'
        text = validated_data['text']
        project = task.project
        if ai_detection_is_configured():
            try:
                result = evaluate_for_project(text, project.ai_detection_strictness)
                if result is not None:
                    ai_score = result.score
                    if result.flagged:
                        initial_status = 'HELD'
            except AIDetectionUnavailable as exc:
                logger.error(
                    'AI detection unavailable for submission by user=%s on task=%s: %s',
                    user.id, task.id, exc,
                )
                initial_status = 'HELD'
        elif not project.is_starter:
            logger.warning('AI detection not configured; submitting without score.')

        submission = Submission.objects.create(
            claim=claim,
            comment_url=validated_data['commentUrl'],
            comment_text_snapshot=text,
            comment_account_handle=(user.handle or user.email.split('@')[0])[:100],
            proof_type='URL',
            paste_event_count=validated_data['pasteCount'],
            pasted_chars=validated_data['pastedChars'],
            keypress_count=validated_data['charsTyped'],
            time_to_compose_seconds=validated_data['elapsedSec'],
            attestation_signed=validated_data['attestationSigned'],
            ai_likelihood_score=ai_score,
            status=initial_status,
        )
        return submission


class SubmissionReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    rating = serializers.IntegerField(min_value=1, max_value=5)
    justification = serializers.CharField(allow_blank=True, required=False, default='')

    def validate(self, attrs):
        if attrs['decision'] == 'rejected' and not (attrs.get('justification') or '').strip():
            raise serializers.ValidationError({'justification': 'Required for rejection'})
        return attrs

    @transaction.atomic
    def apply(self, submission: Submission) -> Submission:
        from accounts.models import User
        from accounts.notifications import (
            notify_real_tasks_unlocked,
            notify_submission_approved,
            notify_submission_rejected,
        )
        decision = self.validated_data['decision']
        is_approved = decision == 'approved'
        project = submission.claim.task.project
        base = project.pay_rate_per_approved_task if is_approved and not project.is_starter else 0
        submission.status = 'APPROVED' if is_approved else 'REJECTED'
        submission.rating_final = self.validated_data['rating']
        submission.justification = self.validated_data.get('justification') or ''
        submission.reviewed_at = timezone.now()
        submission.base_payout = base
        submission.bonus_payout = 0
        submission.save(update_fields=[
            'status', 'rating_final', 'justification',
            'reviewed_at', 'base_payout', 'bonus_payout',
        ])

        worker = submission.claim.user
        unlocked_just_now = False
        if project.is_starter:
            worker_id = submission.claim.user_id
            field = 'starter_approved' if is_approved else 'starter_rejected'
            User.objects.filter(pk=worker_id).update(**{field: F(field) + 1})
            worker.refresh_from_db(fields=['starter_approved', 'status'])
            unlocked_just_now = is_approved and worker.real_tasks_unlocked

        if is_approved:
            notify_submission_approved(submission)
        else:
            notify_submission_rejected(submission, self.validated_data.get('justification') or '')

        if unlocked_just_now and not worker.notifications.filter(kind='real_tasks_unlocked').exists():
            notify_real_tasks_unlocked(worker)

        return submission
