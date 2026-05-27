import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class AIDetectionUnavailable(Exception):
    pass


@dataclass
class AIScoreResult:
    score: Decimal
    flagged: bool
    provider: str


STRICTNESS_THRESHOLDS = {
    'LOW': Decimal('0.90'),
    'MEDIUM': Decimal('0.75'),
    'HIGH': Decimal('0.55'),
}

DEFAULT_THRESHOLD = STRICTNESS_THRESHOLDS['MEDIUM']


def _provider_url() -> str:
    return os.getenv('AI_DETECTION_URL', '').strip()


def _provider_key() -> str:
    return os.getenv('AI_DETECTION_API_KEY', '').strip()


def is_configured() -> bool:
    return bool(_provider_url() and _provider_key())


def score_text(text: str, *, timeout: float = 4.0) -> AIScoreResult:
    if not is_configured():
        raise AIDetectionUnavailable('AI detection service is not configured.')
    url = _provider_url()
    headers = {'Authorization': f'Bearer {_provider_key()}', 'Content-Type': 'application/json'}
    try:
        resp = requests.post(url, json={'text': text}, headers=headers, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.exception('AI detection request failed: %s', exc)
        raise AIDetectionUnavailable(str(exc)) from exc
    raw = body.get('ai_likelihood') if isinstance(body, dict) else None
    if raw is None:
        raise AIDetectionUnavailable('AI detection response missing ai_likelihood field.')
    try:
        score = Decimal(str(raw))
    except (TypeError, ValueError) as exc:
        raise AIDetectionUnavailable(f'AI detection returned non-numeric score: {raw!r}') from exc
    if score < 0 or score > 1:
        raise AIDetectionUnavailable(f'AI detection returned out-of-range score: {score}')
    return AIScoreResult(score=score, flagged=False, provider=body.get('provider') or 'remote')


def evaluate_for_project(text: str, strictness: str) -> Optional[AIScoreResult]:
    threshold = STRICTNESS_THRESHOLDS.get((strictness or '').upper(), DEFAULT_THRESHOLD)
    result = score_text(text)
    result.flagged = result.score >= threshold
    return result
