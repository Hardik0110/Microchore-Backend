from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .models import Notification

if TYPE_CHECKING:
    from submissions.models import Submission
    from .models import User


def _fmt_money(amount) -> str:
    if amount is None:
        return '$0.00'
    try:
        value = Decimal(amount).quantize(Decimal('0.01'))
    except Exception:
        return '$0.00'
    return f"${value}"


def _submission_worker(submission: 'Submission'):
    return submission.claim.user


def notify_submission_approved(submission: 'Submission') -> Notification:
    user = _submission_worker(submission)
    payout = _fmt_money(getattr(submission, 'base_payout', 0) or 0)
    return Notification.objects.create(
        recipient=user,
        kind='submission_approved',
        title='Submission approved',
        body=f'Your reply was approved. You earned {payout}.',
        link='/app/earnings',
    )


def notify_submission_rejected(submission: 'Submission', reason: str = '') -> Notification:
    user = _submission_worker(submission)
    body = reason.strip() if reason else 'Tap to see the reviewer note.'
    return Notification.objects.create(
        recipient=user,
        kind='submission_rejected',
        title='Submission needs another look',
        body=body[:400],
        link='/app/submissions',
    )


def notify_real_tasks_unlocked(user: 'User') -> Notification:
    return Notification.objects.create(
        recipient=user,
        kind='real_tasks_unlocked',
        title='Real tasks unlocked',
        body='You passed the starter set. The marketplace is open.',
        link='/app/marketplace',
    )


def notify_promoted_to_reviewer(user: 'User', tier: str = 'T1') -> Notification:
    return Notification.objects.create(
        recipient=user,
        kind='promoted_to_reviewer',
        title='You are now a reviewer',
        body=f'Tier {tier}. The review queue is available from the sidebar.',
        link='/app/queue',
    )


def notify_account_held(user: 'User', reason: str = '') -> Notification:
    body = reason.strip() if reason else 'Check your account page for details.'
    return Notification.objects.create(
        recipient=user,
        kind='account_held',
        title='Account on hold',
        body=body[:400],
        link='/app/profile',
    )
