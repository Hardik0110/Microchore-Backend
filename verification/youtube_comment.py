from typing import NamedTuple
from urllib.parse import urlparse, parse_qs

import requests
from django.conf import settings


class CommentVerification(NamedTuple):
    ok: bool
    error_code: str = ''
    error_message: str = ''
    video_id: str = ''
    comment_id: str = ''
    author_channel_id: str = ''
    text: str = ''
    published_at: str = ''


def is_configured() -> bool:
    return bool(getattr(settings, 'YOUTUBE_API_KEY', ''))


def extract_video_id(url: str) -> str:
    if not url:
        return ''
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    host = (parsed.hostname or '').lower()
    if 'youtu.be' in host:
        return parsed.path.strip('/').split('/')[0]
    if 'youtube.com' not in host:
        return ''
    params = parse_qs(parsed.query or '')
    v = (params.get('v') or [''])[0]
    if v:
        return v
    parts = [seg for seg in parsed.path.split('/') if seg]
    if len(parts) >= 2 and parts[0] in ('shorts', 'embed', 'v', 'live'):
        return parts[1]
    return ''


def extract_comment_id(url: str) -> str:
    if not url:
        return ''
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    params = parse_qs(parsed.query or '')
    return (params.get('lc') or [''])[0]


def _fetch_thread(comment_id: str):
    return requests.get(
        'https://www.googleapis.com/youtube/v3/commentThreads',
        params={'part': 'snippet', 'id': comment_id, 'key': settings.YOUTUBE_API_KEY},
        timeout=10,
    )


def _fetch_comment(comment_id: str):
    return requests.get(
        'https://www.googleapis.com/youtube/v3/comments',
        params={'part': 'snippet', 'id': comment_id, 'key': settings.YOUTUBE_API_KEY},
        timeout=10,
    )


def verify_comment(comment_url: str, expected_channel_id: str = '', expected_video_id: str = '') -> CommentVerification:
    if not is_configured():
        return CommentVerification(
            ok=False, error_code='not_configured',
            error_message='YouTube comment verification is not configured on this server.',
        )

    comment_id = extract_comment_id(comment_url)
    if not comment_id:
        return CommentVerification(
            ok=False, error_code='no_comment_id',
            error_message=(
                "This URL doesn't include a YouTube comment ID. Click the timestamp under your "
                "comment on YouTube to get a permalink with an 'lc=' parameter."
            ),
        )

    url_video_id = extract_video_id(comment_url)
    author = ''
    text = ''
    published = ''
    actual_video = ''

    try:
        resp = _fetch_thread(comment_id)
    except requests.RequestException as exc:
        return CommentVerification(
            ok=False, error_code='network',
            error_message=f'Could not reach YouTube: {exc}',
            comment_id=comment_id, video_id=url_video_id,
        )

    if resp.status_code == 403:
        return CommentVerification(
            ok=False, error_code='api_forbidden',
            error_message="YouTube API access denied. The server's API key may be invalid or its daily quota is exceeded.",
            comment_id=comment_id, video_id=url_video_id,
        )
    if resp.status_code >= 500:
        return CommentVerification(
            ok=False, error_code='api_unavailable',
            error_message=f'YouTube API is temporarily unavailable (HTTP {resp.status_code}).',
            comment_id=comment_id, video_id=url_video_id,
        )

    items = []
    if resp.ok:
        items = (resp.json() or {}).get('items') or []

    if items:
        thread_snippet = items[0].get('snippet') or {}
        actual_video = (thread_snippet.get('videoId') or '').strip()
        top = (thread_snippet.get('topLevelComment') or {}).get('snippet') or {}
        author = ((top.get('authorChannelId') or {}).get('value') or '').strip()
        text = top.get('textOriginal') or top.get('textDisplay') or ''
        published = top.get('publishedAt') or ''
    else:
        try:
            resp2 = _fetch_comment(comment_id)
        except requests.RequestException as exc:
            return CommentVerification(
                ok=False, error_code='network',
                error_message=f'Could not reach YouTube: {exc}',
                comment_id=comment_id, video_id=url_video_id,
            )
        if not resp2.ok:
            return CommentVerification(
                ok=False, error_code='not_found',
                error_message='Comment not found on YouTube. Make sure the URL is correct and the comment is still public.',
                comment_id=comment_id, video_id=url_video_id,
            )
        items2 = (resp2.json() or {}).get('items') or []
        if not items2:
            return CommentVerification(
                ok=False, error_code='not_found',
                error_message='Comment not found on YouTube. Make sure the URL is correct and the comment is still public.',
                comment_id=comment_id, video_id=url_video_id,
            )
        snippet = items2[0].get('snippet') or {}
        author = ((snippet.get('authorChannelId') or {}).get('value') or '').strip()
        text = snippet.get('textOriginal') or snippet.get('textDisplay') or ''
        published = snippet.get('publishedAt') or ''
        actual_video = url_video_id

    if expected_channel_id and author and author != expected_channel_id:
        return CommentVerification(
            ok=False, error_code='wrong_author',
            error_message='This comment was posted from a different YouTube channel than the one linked to your account.',
            author_channel_id=author, text=text, comment_id=comment_id, video_id=actual_video, published_at=published,
        )

    if expected_video_id and actual_video and expected_video_id != actual_video:
        return CommentVerification(
            ok=False, error_code='wrong_video',
            error_message='This comment belongs to a different YouTube video than the task target.',
            author_channel_id=author, text=text, comment_id=comment_id, video_id=actual_video, published_at=published,
        )

    return CommentVerification(
        ok=True,
        author_channel_id=author, text=text,
        comment_id=comment_id, video_id=actual_video,
        published_at=published,
    )
