"""Twitter OAuth 2.0 (PKCE) helpers for the account-link flow."""
import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import requests as http
from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner


TWITTER_AUTHORIZE_URL = 'https://x.com/i/oauth2/authorize'
TWITTER_TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
TWITTER_USERS_ME_URL = 'https://api.twitter.com/2/users/me'

TWITTER_SCOPES = 'tweet.read users.read offline.access'


def _redirect_uri() -> str:
    return f'{settings.BACKEND_BASE_URL}/api/auth/twitter/callback'

CACHE_PREFIX = 'twitter_oauth:'
CACHE_TTL = 600


def make_pkce():
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return verifier, challenge


def sign_state(user_id: int) -> str:
    signer = TimestampSigner()
    nonce = secrets.token_urlsafe(16)
    return signer.sign(f'{user_id}:{nonce}')


def verify_state(state: str, max_age: int = 600):
    signer = TimestampSigner()
    try:
        payload = signer.unsign(state, max_age=max_age)
        user_id_str = payload.split(':', 1)[0]
        return int(user_id_str)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def stash_verifier(state: str, verifier: str) -> None:
    cache.set(f'{CACHE_PREFIX}{state}', verifier, timeout=CACHE_TTL)


def pop_verifier(state: str):
    key = f'{CACHE_PREFIX}{state}'
    verifier = cache.get(key)
    if verifier:
        cache.delete(key)
    return verifier


def build_authorize_url(state: str, challenge: str) -> str:
    params = {
        'response_type': 'code',
        'client_id': os.getenv('TWITTER_OAUTH_CLIENT_ID', ''),
        'redirect_uri': _redirect_uri(),
        'scope': TWITTER_SCOPES,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return f'{TWITTER_AUTHORIZE_URL}?{urlencode(params)}'


def exchange_code(code: str, verifier: str) -> dict:
    client_id = os.getenv('TWITTER_OAUTH_CLIENT_ID', '')
    client_secret = os.getenv('TWITTER_OAUTH_CLIENT_SECRET', '')
    resp = http.post(
        TWITTER_TOKEN_URL,
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': _redirect_uri(),
            'code_verifier': verifier,
            'client_id': client_id,
        },
        auth=(client_id, client_secret),
        timeout=10,
    )
    if not resp.ok:
        raise ValueError(f'Twitter token exchange failed: {resp.status_code} {resp.text[:200]}')
    data = resp.json()
    if 'access_token' not in data:
        raise ValueError('Twitter token response missing access_token')
    return data


def fetch_user_info(access_token: str) -> dict:
    resp = http.get(
        f'{TWITTER_USERS_ME_URL}?user.fields=created_at,public_metrics,username,name',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    if not resp.ok:
        raise ValueError(f'Twitter user info failed: {resp.status_code} {resp.text[:200]}')
    payload = resp.json()
    data = payload.get('data')
    if not data:
        raise ValueError('Twitter user info response missing data')
    return data
