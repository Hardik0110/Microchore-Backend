import hashlib
import logging
import secrets
from datetime import datetime, timezone as dt_tz
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import twitter_oauth
from .models import SocialAccount
from .serializers import (
    EmailTokenObtainPairSerializer,
    GoogleSignInSerializer,
    LinkYouTubeSerializer,
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
    throttle_scope = 'auth_login'

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
            return Response(status=status.HTTP_205_RESET_CONTENT)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class EmailVerifyRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'email_verify_request'

    def post(self, request):
        if request.user.email_verified:
            return Response({'detail': 'Email already verified.'}, status=status.HTTP_400_BAD_REQUEST)
        code = f'{secrets.randbelow(1_000_000):06d}'
        cache.set(_email_code_cache_key(request.user.id), _hash_code(code), EMAIL_CODE_TTL_SECONDS)
        if settings.DEBUG:
            logger.info('Email verify code for user %s: %s', request.user.id, code)
        else:
            logger.info('Email verify code issued for user %s', request.user.id)
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
        stored = cache.get(key)
        if not stored or stored != _hash_code(code):
            return Response({'detail': 'Invalid or expired code.'}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(key)
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

    def _redirect_with(self, status_key, detail=None):
        params = [f'twitter={status_key}']
        if detail:
            params.append(f'detail={quote(str(detail))[:160]}')
        link_url = f"{settings.FRONTEND_BASE_URL}/onboarding/link-account"
        return redirect(f"{link_url}?{'&'.join(params)}")

    def get(self, request):
        err = request.GET.get('error')
        if err:
            return self._redirect_with('error', request.GET.get('error_description') or err)

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

        try:
            tokens = twitter_oauth.exchange_code(code, verifier)
            tw_user = twitter_oauth.fetch_user_info(tokens['access_token'])
        except ValueError as exc:
            return self._redirect_with('error', str(exc))

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
        clash = (
            SocialAccount.objects
            .filter(platform='X', handle=stored_handle)
            .exclude(user=user)
            .exists()
        )
        if clash:
            return self._redirect_with('error', f'twitter_handle_@{stored_handle}_already_linked')

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

        return self._redirect_with('linked')
