from datetime import datetime, timezone as dt_tz
from typing import NamedTuple
from urllib.parse import urlparse

from django.conf import settings

from .apify import is_configured as apify_is_configured, run_actor_sync


class ProfileVerification(NamedTuple):
    ok: bool
    error_code: str = ''
    error_message: str = ''
    handle: str = ''
    external_id: str = ''
    follower_count: int = 0
    post_count: int = 0
    account_age_days: int = 0


class CommentVerification(NamedTuple):
    ok: bool
    error_code: str = ''
    error_message: str = ''
    author_handle: str = ''
    text: str = ''
    posted_at: str = ''


def _normalize_handle(handle: str) -> str:
    return (handle or '').strip().lstrip('@').lower()[:100]


def normalize_post_url(url: str) -> str:
    if not url:
        return ''
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    host = (parsed.hostname or '').lower()
    if 'instagram.com' not in host:
        return ''
    parts = [seg for seg in parsed.path.split('/') if seg]
    if len(parts) >= 2 and parts[0] in ('p', 'reel', 'reels', 'tv'):
        return f'https://www.instagram.com/{parts[0]}/{parts[1]}/'
    return ''


def verify_profile(handle: str) -> ProfileVerification:
    handle = _normalize_handle(handle)
    if not handle:
        return ProfileVerification(
            ok=False, error_code='no_handle',
            error_message='Enter your Instagram username.',
        )
    if not apify_is_configured():
        return ProfileVerification(
            ok=False, error_code='not_configured',
            error_message='Instagram verification is not configured on this server.',
        )

    actor_id = settings.APIFY_IG_PROFILE_ACTOR
    run_input = {
        'usernames': [handle],
        'resultsType': 'details',
        'resultsLimit': 1,
    }
    res = run_actor_sync(actor_id, run_input, timeout=60)
    if not res.ok:
        return ProfileVerification(
            ok=False, error_code=res.error_code,
            error_message=res.error_message, handle=handle,
        )

    items = res.items or []
    if not items:
        return ProfileVerification(
            ok=False, error_code='not_found',
            error_message=f'Instagram profile @{handle} was not found.',
            handle=handle,
        )

    profile = items[0] if isinstance(items[0], dict) else {}
    real_handle = (profile.get('username') or handle).strip().lower()
    external_id = str(profile.get('id') or profile.get('userId') or '').strip()[:64]
    try:
        followers = int(profile.get('followersCount') or profile.get('followers') or 0)
    except (TypeError, ValueError):
        followers = 0
    try:
        posts = int(profile.get('postsCount') or profile.get('posts') or 0)
    except (TypeError, ValueError):
        posts = 0

    age_days = 0
    joined_at = profile.get('joinedAt') or profile.get('createdAt') or profile.get('joinedDate')
    if joined_at:
        try:
            ts = datetime.fromisoformat(str(joined_at).replace('Z', '+00:00'))
            age_days = max(0, (datetime.now(dt_tz.utc) - ts).days)
        except ValueError:
            age_days = 0

    return ProfileVerification(
        ok=True,
        handle=real_handle,
        external_id=external_id,
        follower_count=followers,
        post_count=posts,
        account_age_days=age_days,
    )


def verify_comment(comment_url: str, expected_handle: str, expected_text: str = '', max_comments: int = 100) -> CommentVerification:
    expected_handle = _normalize_handle(expected_handle)
    if not expected_handle:
        return CommentVerification(
            ok=False, error_code='no_expected_handle',
            error_message='No linked Instagram account to verify against.',
        )
    post_url = normalize_post_url(comment_url)
    if not post_url:
        return CommentVerification(
            ok=False, error_code='bad_url',
            error_message="That doesn't look like an Instagram post URL.",
        )
    if not apify_is_configured():
        return CommentVerification(
            ok=False, error_code='not_configured',
            error_message='Instagram comment verification is not configured on this server.',
        )

    actor_id = settings.APIFY_IG_COMMENT_ACTOR
    run_input = {
        'directUrls': [post_url],
        'resultsLimit': max_comments,
    }
    res = run_actor_sync(actor_id, run_input, timeout=120)
    if not res.ok:
        return CommentVerification(
            ok=False, error_code=res.error_code,
            error_message=res.error_message,
        )

    items = res.items or []
    expected_text_norm = (expected_text or '').strip().lower()

    match = None
    fallback = None
    for raw in items:
        if not isinstance(raw, dict):
            continue
        owner = (raw.get('ownerUsername') or raw.get('username') or raw.get('owner') or '').strip().lower()
        if not owner or owner != expected_handle:
            continue
        text = (raw.get('text') or raw.get('comment') or '').strip()
        timestamp = raw.get('timestamp') or raw.get('createdAt') or ''
        if not fallback:
            fallback = (text, timestamp)
        if expected_text_norm and text.lower() == expected_text_norm:
            match = (text, timestamp)
            break

    chosen = match or fallback
    if not chosen:
        return CommentVerification(
            ok=False, error_code='comment_not_found',
            error_message=(
                f"We couldn't find a comment from @{expected_handle} on this post. "
                "Make sure you posted it and that it hasn't been hidden by Instagram's filters."
            ),
        )

    text, timestamp = chosen
    return CommentVerification(
        ok=True,
        author_handle=expected_handle,
        text=text,
        posted_at=str(timestamp or ''),
    )
