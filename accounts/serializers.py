from django.conf import settings
from django.contrib.auth import get_user_model
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from reviews.permissions import user_is_reviewer

from .models import Notification, SocialAccount

User = get_user_model()


class LinkedAccountSerializer(serializers.ModelSerializer):
    followers = serializers.IntegerField(source='follower_count')
    posts = serializers.IntegerField(source='post_count')
    ageDays = serializers.IntegerField(source='account_age_days')
    verifiedAt = serializers.DateTimeField(source='verified_at')
    platform = serializers.SerializerMethodField()
    passesCredibility = serializers.SerializerMethodField()

    class Meta:
        model = SocialAccount
        fields = ['platform', 'handle', 'followers', 'posts', 'ageDays', 'verifiedAt', 'passesCredibility']

    def get_platform(self, obj):
        return {'IG': 'instagram', 'YT': 'youtube', 'TIKTOK': 'tiktok', 'X': 'x'}.get(obj.platform, obj.platform.lower())

    def get_passesCredibility(self, obj):
        if obj.platform == 'IG':
            return obj.follower_count >= 100 and obj.post_count >= 10
        return True


class UserSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source='date_joined', read_only=True)
    emailVerified = serializers.BooleanField(source='email_verified')
    wizardStep = serializers.CharField(source='wizard_step')
    starterApproved = serializers.IntegerField(source='starter_approved')
    starterRejected = serializers.IntegerField(source='starter_rejected')
    realTasksUnlocked = serializers.BooleanField(source='real_tasks_unlocked', read_only=True)
    holdReason = serializers.SerializerMethodField()
    payoutMethod = serializers.CharField(allow_null=True, required=False)
    payoutHandle = serializers.CharField(source='payout_handle', allow_null=True, required=False)
    attestedAt = serializers.DateTimeField(source='attested_at', allow_null=True, required=False)
    tutorialCompletedAt = serializers.DateTimeField(source='tutorial_completed_at', allow_null=True, required=False)
    linkedAccount = serializers.SerializerMethodField()
    isReviewer = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'handle', 'country', 'role', 'createdAt',
            'emailVerified', 'wizardStep',
            'starterApproved', 'starterRejected', 'realTasksUnlocked',
            'holdReason', 'payoutMethod', 'payoutHandle',
            'attestedAt', 'tutorialCompletedAt', 'linkedAccount', 'isReviewer',
        ]
        read_only_fields = [
            'id', 'email', 'role', 'createdAt', 'realTasksUnlocked',
            'emailVerified', 'wizardStep', 'starterApproved', 'starterRejected',
            'isReviewer',
        ]

    def get_holdReason(self, obj):
        if obj.status != 'HELD':
            return None
        last_hold = obj.holds.order_by('-started_at').first()
        return last_hold.reason if last_hold else 'Account on hold'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['payoutMethod'] = instance.payout_method.lower() if instance.payout_method else None
        return data

    def validate_payoutMethod(self, value):
        if value in (None, ''):
            return None
        normalized = value.strip().upper()
        if normalized not in {'AIRTM', 'PAYPAL', 'CRYPTO'}:
            raise serializers.ValidationError('Must be one of: airtm, paypal, crypto.')
        return normalized

    def update(self, instance, validated_data):
        if 'payoutMethod' in validated_data:
            instance.payout_method = validated_data.pop('payoutMethod')
        return super().update(instance, validated_data)

    def get_linkedAccount(self, obj):
        acct = obj.social_accounts.filter(is_active=True).order_by('-last_snapshot_at').first()
        if not acct:
            return None
        return LinkedAccountSerializer(acct).data

    def get_isReviewer(self, obj):
        return user_is_reviewer(obj)


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    handle = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = User
        fields = ['email', 'password', 'handle', 'country']
        extra_kwargs = {
            'email': {'required': True},
            'country': {'required': False, 'allow_blank': True, 'default': ''},
        }

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def create(self, validated):
        email = validated['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated['password'],
            handle=validated.get('handle', ''),
            country=validated.get('country', ''),
            email_verified=True,
            wizard_step='welcome',
        )
        return user


class EmailTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = (attrs.get('email') or '').lower().strip()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({'detail': 'No active account found with the given credentials.'})
        if not user.is_active:
            raise serializers.ValidationError({'detail': 'Account is disabled.'})
        if not user.check_password(attrs.get('password')):
            raise serializers.ValidationError({'detail': 'Incorrect password.'})
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }


def issue_tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'user': UserSerializer(user).data,
    }


class LinkYouTubeSerializer(serializers.Serializer):
    """Exchanges a YouTube OAuth access token for a verified SocialAccount link."""
    access_token = serializers.CharField(write_only=True)

    def validate(self, attrs):
        import requests as http
        from datetime import datetime, timezone as dt_tz
        from django.utils import timezone

        access_token = attrs['access_token']

        try:
            resp = http.get(
                'https://www.googleapis.com/youtube/v3/channels',
                params={'part': 'snippet,statistics', 'mine': 'true'},
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
            )
        except http.RequestException as exc:
            raise serializers.ValidationError({'detail': f'Could not reach YouTube: {exc}'})

        if resp.status_code == 401:
            raise serializers.ValidationError(
                {'detail': 'YouTube access token is invalid or expired. Please reconnect.'}
            )
        if resp.status_code == 403:
            raise serializers.ValidationError(
                {'detail': 'YouTube API access denied. Make sure YouTube Data API v3 is enabled.'}
            )
        if not resp.ok:
            raise serializers.ValidationError(
                {'detail': f'YouTube API returned {resp.status_code}: {resp.text[:200]}'}
            )

        data = resp.json()
        items = data.get('items') or []
        if not items:
            raise serializers.ValidationError(
                {'detail': 'No YouTube channel found on this Google account.'}
            )

        channel = items[0]
        snippet = channel.get('snippet') or {}
        stats = channel.get('statistics') or {}

        handle = snippet.get('customUrl') or snippet.get('title') or ''
        if handle and not handle.startswith('@'):
            handle = f'@{handle.lstrip("@")}'

        try:
            followers = int(stats.get('subscriberCount') or 0)
        except (TypeError, ValueError):
            followers = 0
        try:
            videos = int(stats.get('videoCount') or 0)
        except (TypeError, ValueError):
            videos = 0

        published_at_str = snippet.get('publishedAt')
        if published_at_str:
            try:
                published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                age_days = max(0, (datetime.now(dt_tz.utc) - published_at).days)
            except ValueError:
                age_days = 0
        else:
            age_days = 0

        request = self.context.get('request')
        user = request.user if request else None
        if user is None or not user.is_authenticated:
            raise serializers.ValidationError({'detail': 'Not authenticated.'})

        stored_handle = handle.lstrip('@')[:100]
        clash = (
            SocialAccount.objects
            .filter(platform='YT', handle=stored_handle)
            .exclude(user=user)
            .exists()
        )
        if clash:
            raise serializers.ValidationError({
                'detail': f'This YouTube channel (@{stored_handle}) is already linked to another Microchore account.',
            })

        social, _ = SocialAccount.objects.update_or_create(
            user=user,
            platform='YT',
            defaults={
                'handle': stored_handle,
                'follower_count': followers,
                'post_count': videos,
                'account_age_days': age_days,
                'verified_at': timezone.now(),
                'is_active': True,
            },
        )

        return {
            'linkedAccount': LinkedAccountSerializer(social).data,
        }


class GoogleSignInSerializer(serializers.Serializer):
    credential = serializers.CharField(write_only=True)

    def validate(self, attrs):
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            raise serializers.ValidationError(
                {'detail': 'Google sign-in is not configured on this server.'}
            )

        try:
            idinfo = google_id_token.verify_oauth2_token(
                attrs['credential'],
                google_requests.Request(),
                client_id,
                clock_skew_in_seconds=30,
            )
        except ValueError as exc:
            raise serializers.ValidationError({'detail': f'Invalid Google token: {exc}'})

        if idinfo.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
            raise serializers.ValidationError({'detail': 'Token issuer is not Google.'})

        email = (idinfo.get('email') or '').lower().strip()
        if not email:
            raise serializers.ValidationError({'detail': 'Google token had no email claim.'})
        if not idinfo.get('email_verified', False):
            raise serializers.ValidationError({'detail': 'Google reports this email is not verified.'})

        given_name = (idinfo.get('given_name') or '').strip()
        family_name = (idinfo.get('family_name') or '').strip()
        handle = given_name or email.split('@')[0]

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                username=email,
                email=email,
                handle=handle,
                first_name=given_name[:30],
                last_name=family_name[:30],
                email_verified=True,
                wizard_step='welcome',
            )
            user.set_unusable_password()
            user.save(update_fields=['password'])
        else:
            updates = {}
            if not user.email_verified:
                updates['email_verified'] = True
            if not user.handle:
                updates['handle'] = handle
            if updates:
                for k, v in updates.items():
                    setattr(user, k, v)
                user.save(update_fields=list(updates.keys()))

        if not user.is_active:
            raise serializers.ValidationError({'detail': 'Account is disabled.'})

        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }


class NotificationSerializer(serializers.ModelSerializer):
    isRead = serializers.BooleanField(source='is_read', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    readAt = serializers.DateTimeField(source='read_at', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'kind', 'title', 'body', 'link', 'isRead', 'createdAt', 'readAt']
        read_only_fields = fields
