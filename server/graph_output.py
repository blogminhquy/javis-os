"""Remove Graph credentials at the public-output boundary, without mutating API data."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

_SECRET_KEYS = frozenset({
    "access_token", "input_token", "appsecret_proof", "app_secret", "client_secret",
    "refresh_token", "fb_exchange_token", "authorization", "client_token",
})
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"((?:access_token|input_token|appsecret_proof|app_secret|client_secret|refresh_token|"
    r"fb_exchange_token|client_token)\s*[=:]\s*)([^\s&,;\"'<>]+)", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+[^\s,;\"'<>]+", re.IGNORECASE)


def _key(value):
    return unquote(str(value)).casefold().replace("-", "_")


def _url(match):
    original = match.group(0)
    try:
        parts = urlsplit(original)
        query = parse_qsl(parts.query, keep_blank_values=True)
        safe = [(k, v) for k, v in query if _key(k) not in _SECRET_KEYS]
        fragment = parse_qsl(parts.fragment, keep_blank_values=True)
        safe_fragment = [(k, v) for k, v in fragment if _key(k) not in _SECRET_KEYS]
        if safe == query and safe_fragment == fragment:
            return original
        return urlunsplit((parts.scheme, parts.netloc, parts.path,
                           urlencode(safe), urlencode(safe_fragment)))
    except ValueError:
        return "[invalid Graph URL removed]"


def sanitize_graph_output(value):
    """Keep pagination cursors and public fields; remove secrets even in nested errors."""
    if isinstance(value, dict):
        return {key: sanitize_graph_output(item) for key, item in value.items()
                if _key(key) not in _SECRET_KEYS}
    if isinstance(value, (list, tuple)):
        return [sanitize_graph_output(item) for item in value]
    if isinstance(value, str):
        value = _URL.sub(_url, value)
        value = _ASSIGNMENT.sub(lambda m: m.group(1) + "[REDACTED]", value)
        return _BEARER.sub("Bearer [REDACTED]", value)
    return value
