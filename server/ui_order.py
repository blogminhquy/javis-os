"""The owner's own order of lists that have no table of their own (0.454.0): the tags of the Partners page and of the
Teams page.

Owner, 2026-11-04: "sắp xếp thứ tự Project kéo thả như Brain ... các tag và các project hoặc ghim và cả đoạn chat".
Projects and pinned chats keep their order in the session store (sort_order, pin_order). Tags live inside each agent
file and each team row, so their order is a list of tag KEYS per page, in settings.json under "ui_order", like the
brain order (brain_order.py): every device that opens this Javis shows the same order. A tag not in the list comes
after the ordered ones, by name.
"""
from __future__ import annotations

SETTINGS_KEY = "ui_order"
SCOPES = ("tags_agents", "tags_teams")
MAX_ITEMS = 500
MAX_KEY = 120


def clean(order) -> list:
    """Distinct non-empty strings, each at most MAX_KEY characters, at most MAX_ITEMS of them."""
    out, seen = [], set()
    for x in order if isinstance(order, list) else []:
        if not isinstance(x, str):
            continue
        k = x.strip()[:MAX_KEY]
        if k and k not in seen:
            seen.add(k)
            out.append(k)
        if len(out) >= MAX_ITEMS:
            break
    return out


def read(settings: dict) -> dict:
    """{scope: [keys]} for every known scope (empty when never ordered)."""
    raw = (settings or {}).get(SETTINGS_KEY)
    raw = raw if isinstance(raw, dict) else {}
    return {s: clean(raw.get(s)) for s in SCOPES}


def updated(settings: dict, scope: str, order) -> dict:
    """The whole "ui_order" value with `scope` replaced. Raises ValueError for an unknown scope."""
    if scope not in SCOPES:
        raise ValueError(scope)
    cur = read(settings)
    cur[scope] = clean(order)
    return cur
