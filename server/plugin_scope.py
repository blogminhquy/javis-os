"""Brain availability for shared user plugins; absent entry means global (legacy behavior)."""
import json
from pathlib import Path

from config import STATE_DIR

PATH = STATE_DIR / "plugin-scopes.json"


def _read():
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or any(
            not isinstance(value, list) or not all(isinstance(root, str) for root in value)
            for value in data.values()
        ):
            return {"*": []}
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # Corrupt policy must not broaden access to every brain.
        return {"*": []}


_CACHE = (None, None)


def read():
    global _CACHE
    try:
        st = PATH.stat()
        sig = (str(PATH), st.st_mtime_ns, st.st_size)
    except OSError:
        sig = (str(PATH), None)
    if _CACHE[0] != sig:
        _CACHE = (sig, _read())
    return _CACHE[1]


def selection(slug):
    data = read()
    return data.get(slug, data.get("*"))


def allowed(slug, root):
    targets = selection(slug)
    if targets is None:
        return True
    if not isinstance(targets, list) or not root:
        return False
    return str(Path(root).resolve()) in targets


def invalidate():
    global _CACHE
    _CACHE = (None, None)
