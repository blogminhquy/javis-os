"""Pure delivery classification and bounded exponential retry policy."""
from email.utils import parsedate_to_datetime
import math


def classify_delivery(status_code: int | None, retry_after: str | None, now: float) -> dict:
    kind = ('accepted' if status_code in (200, 201) else
            'retry' if status_code is None or status_code in (408, 429) or 500 <= status_code <= 599
            else 'blocked')
    delay = None
    if retry_after:
        value = retry_after.strip()
        try:
            if value.isascii() and value.isdigit():
                delay = float(value)
            else:
                delay = max(0.0, parsedate_to_datetime(value).timestamp() - now)
            if not math.isfinite(delay):
                delay = None
        except (ValueError, TypeError, OverflowError):
            delay = None
    return {'kind': kind, 'code': '' if kind == 'accepted' else
            'provider_unavailable' if status_code is None else f'provider_http_{status_code}',
            'retry_after_seconds': delay}


def retry_delay(attempt: int, retry_after_seconds: float | None, jitter: float) -> float:
    base = min(300, 5 * 2 ** min(max(0, attempt), 6))
    return max(base * (1 + 0.2 * min(1, max(0, jitter))), retry_after_seconds or 0)
