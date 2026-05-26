from urllib.parse import urlparse

from rest_framework import serializers

from .models import Task


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
