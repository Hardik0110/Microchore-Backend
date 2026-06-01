from typing import Any, NamedTuple

import requests
from django.conf import settings


APIFY_BASE = 'https://api.apify.com/v2'


class ActorRunResult(NamedTuple):
    ok: bool
    error_code: str = ''
    error_message: str = ''
    items: list = []
    status_code: int = 0


def is_configured() -> bool:
    return bool(getattr(settings, 'APIFY_API_TOKEN', ''))


def run_actor_sync(actor_id: str, run_input: dict[str, Any], timeout: int = 60) -> ActorRunResult:
    if not is_configured():
        return ActorRunResult(
            ok=False, error_code='not_configured',
            error_message='Apify is not configured on this server.',
        )

    url = f'{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items'
    headers = {
        'Authorization': f'Bearer {settings.APIFY_API_TOKEN}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(url, headers=headers, json=run_input, timeout=timeout)
    except requests.RequestException as exc:
        return ActorRunResult(
            ok=False, error_code='network',
            error_message=f'Could not reach Apify: {exc}',
        )

    if resp.status_code == 401:
        return ActorRunResult(
            ok=False, error_code='unauthorized', status_code=401,
            error_message="Apify API token is invalid or missing.",
        )
    if resp.status_code == 402:
        return ActorRunResult(
            ok=False, error_code='out_of_credits', status_code=402,
            error_message="Apify account is out of credits.",
        )
    if resp.status_code == 404:
        return ActorRunResult(
            ok=False, error_code='actor_not_found', status_code=404,
            error_message=f'Apify actor "{actor_id}" not found.',
        )
    if resp.status_code >= 500:
        return ActorRunResult(
            ok=False, error_code='api_unavailable', status_code=resp.status_code,
            error_message=f'Apify is temporarily unavailable (HTTP {resp.status_code}).',
        )
    if not resp.ok:
        return ActorRunResult(
            ok=False, error_code='api_error', status_code=resp.status_code,
            error_message=f'Apify returned HTTP {resp.status_code}.',
        )

    try:
        data = resp.json()
    except ValueError:
        return ActorRunResult(
            ok=False, error_code='bad_response', status_code=resp.status_code,
            error_message='Apify returned a non-JSON response.',
        )

    if not isinstance(data, list):
        return ActorRunResult(
            ok=False, error_code='bad_response', status_code=resp.status_code,
            error_message='Apify returned an unexpected payload shape.',
        )

    return ActorRunResult(ok=True, items=data, status_code=resp.status_code)
