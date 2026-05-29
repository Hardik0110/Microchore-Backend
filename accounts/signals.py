"""BE-001: revoke a user's refresh tokens the moment they are banned.

Access tokens are already rejected for BANNED users by
``StatusAwareJWTAuthentication``; this closes the remaining gap by
blacklisting every outstanding *refresh* token on the ACTIVE/HELD -> BANNED
transition so a banned account cannot mint new access tokens.
"""
import logging

from django.db.models.signals import pre_save

logger = logging.getLogger(__name__)


def _blacklist_all_refresh_tokens(user) -> int:
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
    except Exception:  # token_blacklist app not installed
        logger.warning('Token blacklist app unavailable; cannot revoke tokens for user %s', user.pk)
        return 0

    revoked = 0
    for token in OutstandingToken.objects.filter(user_id=user.pk):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        if created:
            revoked += 1
    return revoked


def revoke_tokens_on_ban(sender, instance, **kwargs):
    if not instance.pk:
        return  # new account; no tokens yet
    if getattr(instance, 'status', None) != 'BANNED':
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if previous.status == 'BANNED':
        return  # already banned; tokens handled on the original transition
    revoked = _blacklist_all_refresh_tokens(instance)
    logger.info('User %s banned: revoked %d outstanding refresh token(s).', instance.pk, revoked)


def connect(user_model):
    pre_save.connect(
        revoke_tokens_on_ban,
        sender=user_model,
        dispatch_uid='accounts.revoke_tokens_on_ban',
    )
