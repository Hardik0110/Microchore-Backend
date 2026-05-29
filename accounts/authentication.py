from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class StatusAwareJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        status = getattr(user, 'status', None)
        if status == 'BANNED':
            raise AuthenticationFailed('Account banned.', code='account_banned')
        return user
