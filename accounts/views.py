import hashlib
import logging
import secrets
from datetime import datetime, timezone as dt_tz
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import twitter_oauth
from .models import Notification, SocialAccount
from .serializers import (
    EmailTokenObtainPairSerializer,
    GoogleSignInSerializer,
    LinkYouTubeSerializer,
    NotificationSerializer,
    SignupSerializer,
    UserSerializer,
    issue_tokens_for,
)


logger = logging.getLogger(__name__)


EMAIL_CODE_TTL_SECONDS = 15 * 60


def _email_code_cache_key(user_id: int) -> str:
    return f'email-verify:{user_id}'


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


class SignupView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_signup'

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(issue_tokens_for(user), status=status.HTTP_201_CREATED)


class GoogleSignInView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_google'

    def post(self, request):
        serializer = GoogleSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'patch']

    def get_object(self):
        return self.request.user


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_login'


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_logout'

    def post(self, request):
        refresh_token = request.data.get('refresh') if isinstance(request.data, dict) else None
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {'detail': 'Invalid or expired refresh token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Unexpected error during logout token blacklist.')
            return Response(
                {'detail': 'Logout failed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_200_OK)


class StatusAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """BE-001: reject token refresh for banned/disabled accounts.

    The default serializer never loads the user, so a BANNED user holding a
    valid refresh token could otherwise mint fresh access tokens until the
    refresh token expired (up to 7 days).
    """

    def validate(self, attrs):
        token = RefreshToken(attrs['refresh'])  # validates signature/expiry/blacklist
        user_id = token.get(jwt_settings.USER_ID_CLAIM)
        User = get_user_model()
        try:
            user = User.objects.get(**{jwt_settings.USER_ID_FIELD: user_id})
        except User.DoesNotExist:
            raise InvalidToken('No active account found for this token.')
        if getattr(user, 'status', None) == 'BANNED' or not user.is_active:
            raise InvalidToken('Account is not permitted to refresh tokens.')
        return super().validate(attrs)


class ThrottledTokenRefreshView(TokenRefreshView):
    serializer_class = StatusAwareTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_refresh'


class EmailVerifyRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'email_verify_request'

    def post(self, request):
        if request.user.email_verified:
            return Response({'detail': 'Email already verified.'}, status=status.HTTP_400_BAD_REQUEST)
        code = f'{secrets.randbelow(1_000_000):06d}'
        cache.set(_email_code_cache_key(request.user.id), _hash_code(code), EMAIL_CODE_TTL_SECONDS)
        subject = 'Your Microchore verification code'
        body = (
            f'Hi,\n\n'
            f'Your Microchore verification code is: {code}\n\n'
            f'It expires in {EMAIL_CODE_TTL_SECONDS // 60} minutes. If you did not request this, you can ignore this email.\n\n'
            f'- Microchore'
        )
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception('Failed to send verification email to user %s', request.user.id)
            if settings.DEBUG:
                logger.info('Email verify code for user %s (mail failed): %s', request.user.id, code)
            return Response(
                {'detail': 'Could not send verification email. Try again in a moment.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        logger.info('Email verify code sent to user %s', request.user.id)
        return Response({'sent': True})


class EmailVerifyConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'email_verify_confirm'

    def post(self, request):
        code = (request.data.get('code') or '').strip() if isinstance(request.data, dict) else ''
        if not code.isdigit() or len(code) != 6:
            return Response({'detail': 'Invalid code format.'}, status=status.HTTP_400_BAD_REQUEST)
        key = _email_code_cache_key(request.user.id)
        attempt_key = f'{key}:attempts'
        attempts = cache.get(attempt_key) or 0
        if attempts >= 5:
            cache.delete(key)
            return Response(
                {'detail': 'Too many invalid attempts. Request a new code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        stored = cache.get(key)
        if not stored or stored != _hash_code(code):
            cache.set(attempt_key, attempts + 1, EMAIL_CODE_TTL_SECONDS)
            return Response({'detail': 'Invalid or expired code.'}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(key)
        cache.delete(attempt_key)
        request.user.email_verified = True
        request.user.save(update_fields=['email_verified'])
        return Response(UserSerializer(request.user).data)


class LinkYouTubeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LinkYouTubeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class TwitterStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        verifier, challenge = twitter_oauth.make_pkce()
        state = twitter_oauth.sign_state(request.user.id)
        twitter_oauth.stash_verifier(state, verifier)
        authorize_url = twitter_oauth.build_authorize_url(state, challenge)
        return Response({'authorize_url': authorize_url})


class TwitterCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    _ALLOWED_CODES = {
        'oauth_error',
        'missing_code_or_state',
        'invalid_or_expired_state',
        'pkce_verifier_missing',
        'user_not_found',
        'exchange_failed',
        'handle_clash',
        'account_inactive',
    }

    def _redirect_with(self, status_key, code=None):
        params = [f'twitter={status_key}']
        if code and code in self._ALLOWED_CODES:
            params.append(f'code={quote(code)}')
        link_url = f"{settings.FRONTEND_BASE_URL}/onboarding/link-account"
        return redirect(f"{link_url}?{'&'.join(params)}")

    def get(self, request):
        err = request.GET.get('error')
        if err:
            logger.warning('Twitter callback upstream error: %s', err)
            return self._redirect_with('error', 'oauth_error')

        code = request.GET.get('code')
        state = request.GET.get('state')
        if not code or not state:
            return self._redirect_with('error', 'missing_code_or_state')

        user_id = twitter_oauth.verify_state(state)
        if not user_id:
            return self._redirect_with('error', 'invalid_or_expired_state')

        verifier = twitter_oauth.pop_verifier(state)
        if not verifier:
            return self._redirect_with('error', 'pkce_verifier_missing')

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return self._redirect_with('error', 'user_not_found')

        if getattr(user, 'status', None) != 'ACTIVE':
            return self._redirect_with('error', 'account_inactive')

        try:
            tokens = twitter_oauth.exchange_code(code, verifier)
            tw_user = twitter_oauth.fetch_user_info(tokens['access_token'])
        except ValueError:
            logger.exception('Twitter token exchange failed.')
            return self._redirect_with('error', 'exchange_failed')

        username = (tw_user.get('username') or '').strip()
        metrics = tw_user.get('public_metrics') or {}
        try:
            followers = int(metrics.get('followers_count') or 0)
        except (TypeError, ValueError):
            followers = 0
        try:
            tweets = int(metrics.get('tweet_count') or 0)
        except (TypeError, ValueError):
            tweets = 0

        created_str = tw_user.get('created_at')
        age_days = 0
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                age_days = max(0, (datetime.now(dt_tz.utc) - created).days)
            except ValueError:
                age_days = 0

        stored_handle = username[:100]
        from django.db import IntegrityError, transaction as _tx
        try:
            with _tx.atomic():
                clash = (
                    SocialAccount.objects
                    .select_for_update()
                    .filter(platform='X', handle=stored_handle)
                    .exclude(user=user)
                    .exists()
                )
                if clash:
                    return self._redirect_with('error', 'handle_clash')
                SocialAccount.objects.update_or_create(
                    user=user,
                    platform='X',
                    defaults={
                        'handle': stored_handle,
                        'follower_count': followers,
                        'post_count': tweets,
                        'account_age_days': age_days,
                        'verified_at': timezone.now(),
                        'is_active': True,
                    },
                )
        except IntegrityError:
            return self._redirect_with('error', 'handle_clash')

        return self._redirect_with('linked')


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user).order_by('-created_at')
        unread_only = self.request.query_params.get('unread')
        if unread_only in ('1', 'true', 'yes'):
            qs = qs.filter(is_read=False)
        return qs[:50]

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'results': serializer.data, 'unreadCount': unread_count})


class NotificationMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            notif = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at'])
        return Response(NotificationSerializer(notif).data)


class NotificationMarkAllReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user, is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        return Response({'updated': updated})
