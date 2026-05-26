from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from projects.models import Task

from .models import Claim, Submission


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

    def validate_taskId(self, value):
        if not Task.objects.filter(pk=value).exists():
            raise serializers.ValidationError('Task does not exist')
        return value

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        task = Task.objects.select_for_update().get(pk=validated_data['taskId'])

        if Submission.objects.filter(claim__user=user, claim__task=task).exists():
            raise serializers.ValidationError({
                'taskId': 'You have already submitted on this task.',
            })

        if task.project.is_starter:
            claim, _ = Claim.objects.get_or_create(
                task=task,
                user=user,
                status='ACTIVE',
                defaults={'expires_at': timezone.now() + timedelta(hours=24)},
            )
        else:
            claim = Claim.objects.filter(task=task, user=user, status='ACTIVE').first()
            if not claim:
                raise serializers.ValidationError({'taskId': 'You must claim this task before making a submission.'})

        claim.status = 'SUBMITTED'
        claim.save(update_fields=['status'])

        submission = Submission.objects.create(
            claim=claim,
            comment_url=validated_data['commentUrl'],
            comment_text_snapshot=validated_data['text'],
            comment_account_handle=(user.handle or user.email.split('@')[0])[:100],
            proof_type='URL',
            paste_event_count=validated_data['pasteCount'],
            pasted_chars=validated_data['pastedChars'],
            keypress_count=validated_data['charsTyped'],
            time_to_compose_seconds=validated_data['elapsedSec'],
            attestation_signed=validated_data['attestationSigned'],
            status='PENDING',
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
        submission.save()
        if project.is_starter:
            worker = submission.claim.user
            if is_approved:
                worker.starter_approved = (worker.starter_approved or 0) + 1
            else:
                worker.starter_rejected = (worker.starter_rejected or 0) + 1
            worker.save(update_fields=['starter_approved', 'starter_rejected'])
        return submission
