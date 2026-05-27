from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Company, Project, Task


STATUS_TO_FE = {'DRAFT': 'draft', 'ACTIVE': 'active', 'PAUSED': 'paused', 'COMPLETE': 'paused'}
STATUS_TO_DB = {'draft': 'DRAFT', 'active': 'ACTIVE', 'paused': 'PAUSED'}
CADENCE_TO_DB = {'weekly': 'WEEKLY', 'biweekly': 'BIWEEKLY', 'monthly': 'MONTHLY'}
METHOD_TO_DB = {'paypal': 'PAYPAL', 'airtm': 'AIRTM', 'crypto': 'CRYPTO', 'any': 'ANY'}
VALID_TONES = ('lifestyle', 'product', 'story', 'disagreement', 'brand')


def platform_from_url(url: str) -> str:
    if not url:
        return 'instagram'
    try:
        host = (urlparse(url).hostname or '').lower()
    except Exception:
        return 'instagram'
    if 'tiktok' in host:
        return 'tiktok'
    if 'soundcloud' in host:
        return 'soundcloud'
    if 'youtube' in host or 'youtu.be' in host:
        return 'youtube'
    if host in ('twitter.com', 'x.com') or host.endswith('.x.com'):
        return 'x'
    return 'instagram'


_POST_TYPE_SEGMENTS = {'p', 'reel', 'reels', 'shorts', 'video', 'watch', 'tracks', 'track', 'status'}


def handle_from_url(url: str) -> str:
    if not url:
        return ''
    try:
        path = (urlparse(url).path or '').strip('/')
    except Exception:
        return ''
    if not path:
        return ''
    first = path.split('/')[0]
    if first.lower() in _POST_TYPE_SEGMENTS:
        return ''
    if first.startswith('@'):
        return first
    return f'@{first}' if first else ''


class TaskListSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    projectId = serializers.IntegerField(source='project_id', read_only=True)
    platform = serializers.SerializerMethodField()
    targetHandle = serializers.SerializerMethodField()
    targetUrl = serializers.SerializerMethodField()
    brief = serializers.CharField(source='project.brief_md', read_only=True)
    keyword = serializers.SerializerMethodField()
    payRate = serializers.DecimalField(
        source='project.pay_rate_per_approved_task', max_digits=10, decimal_places=4, read_only=True
    )
    payoutCadence = serializers.SerializerMethodField()
    payoutMin = serializers.DecimalField(
        source='project.payout_min_threshold', max_digits=10, decimal_places=2, read_only=True
    )
    payoutMethod = serializers.SerializerMethodField()
    remaining = serializers.IntegerField(source='remaining_count', read_only=True)
    total = serializers.IntegerField(source='total_count', read_only=True)
    tone = serializers.CharField(source='project.tone', read_only=True)
    expiresAt = serializers.DateTimeField(source='expires_at', read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'kind', 'projectId', 'platform', 'targetHandle', 'targetUrl',
            'brief', 'keyword', 'payRate', 'payoutCadence', 'payoutMin', 'payoutMethod',
            'remaining', 'total', 'tone', 'expiresAt',
        ]

    def get_kind(self, obj):
        return 'starter' if obj.project.is_starter else 'real'

    def _effective_url(self, obj):
        return obj.target_post_url or obj.project.target_post_url_default or ''

    def get_platform(self, obj):
        return platform_from_url(self._effective_url(obj))

    def get_targetHandle(self, obj):
        parsed = handle_from_url(self._effective_url(obj))
        if parsed:
            return parsed
        if obj.project.is_starter:
            return '@microchore.practice'
        return ''

    def get_targetUrl(self, obj):
        return self._effective_url(obj)

    def get_keyword(self, obj):
        return obj.keyword or obj.project.keyword_default or ''

    def get_payoutCadence(self, obj):
        return (obj.project.payout_cadence or 'WEEKLY').lower()

    def get_payoutMethod(self, obj):
        return (obj.project.payout_method_required or 'ANY').lower()


class ProjectSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    companyName = serializers.CharField(source='company.name', read_only=True)
    description = serializers.CharField(source='brief_md', read_only=True)
    targetUrl = serializers.URLField(source='target_post_url_default', read_only=True)
    payRate = serializers.DecimalField(
        source='pay_rate_per_approved_task',
        max_digits=10,
        decimal_places=4,
        coerce_to_string=False,
        read_only=True,
    )
    status = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'companyName', 'name', 'description', 'targetUrl', 'payRate', 'status', 'createdAt']

    def get_id(self, obj):
        return str(obj.pk)

    def get_status(self, obj):
        return STATUS_TO_FE.get(obj.status, 'draft')


class ProjectCreateSerializer(serializers.Serializer):
    companyName = serializers.CharField(max_length=255)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField()
    targetUrl = serializers.URLField()
    payRate = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=Decimal('0.0001'))

    @transaction.atomic
    def create(self, validated_data):
        company_name = validated_data['companyName'].strip()
        company, _ = Company.objects.get_or_create(name=company_name)
        project = Project.objects.create(
            company=company,
            name=validated_data['name'].strip(),
            is_starter=False,
            tone='product',
            status='ACTIVE',
            brief_md=validated_data['description'].strip(),
            tone_guidance='',
            target_post_url_default=validated_data['targetUrl'],
            keyword_default=None,
            pay_rate_per_approved_task=validated_data['payRate'],
            payout_cadence='WEEKLY',
            payout_method_required='ANY',
            payout_min_threshold=Decimal('5.00'),
            terms_md='Standard terms.',
            ai_detection_strictness='MEDIUM',
            credibility_thresholds={},
        )
        return project


class ProjectStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['active', 'paused', 'draft'])

    def update(self, instance: Project, validated_data):
        instance.status = STATUS_TO_DB[validated_data['status']]
        instance.save(update_fields=['status'])
        return instance


class ProjectTaskCreateSerializer(serializers.Serializer):
    keyword = serializers.CharField(max_length=100)
    tone = serializers.ChoiceField(choices=VALID_TONES)
    totalSlots = serializers.IntegerField(min_value=1)

    @transaction.atomic
    def create(self, validated_data):
        project: Project = self.context['project']
        if not project.tone or project.tone == 'product':
            project.tone = validated_data['tone']
        if project.status == 'DRAFT':
            project.status = 'ACTIVE'
        project.save()
        task = Task.objects.create(
            project=project,
            status='OPEN',
            target_post_url=None,
            keyword=validated_data['keyword'],
            remaining_count=validated_data['totalSlots'],
            total_count=validated_data['totalSlots'],
            expires_at=timezone.now() + timedelta(days=30),
        )
        return task
