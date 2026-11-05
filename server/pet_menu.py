"""The owner's own mascot menu (dashboard/pet-menu.js): which Javis features the pet opens, in which order.

Owner, 2026-11-05: "Chỉ cần thêm và sắp xếp vị trí thôi là ok rồi. Và cho phần này vào trong phần cài đặt linh vật."
So a save may only ADD features and REORDER them. Renaming, changing an icon or an action, removing, hiding and
"restore defaults" are out of scope, and this module refuses a save that would drop an item already saved.

Stored in settings.json under "pet_menu", apart from dashboard.pet: the pet's look is written on every drag of the
pet, and a stale window resending an old menu there would quietly undo a newer one. Here every save carries the
revision it was edited from, and a save made from an older revision is refused as a conflict.

    {"schemaVersion": 1, "rev": 3, "items": [{"actionId": "chat"}, ...]}

The array order is the menu order. Names and icons come from the catalog in pet-menu.js, never from here.
"""
from __future__ import annotations

import re

SETTINGS_KEY = "pet_menu"
SCHEMA_VERSION = 1
MAX_ITEMS = 60

# The menu the pet showed before this setting existed, in that order. A Javis that never saved a menu keeps it.
DEFAULT_ITEMS = ("chat", "agent", "workflow", "mic", "pet", "teams")
# Every action a save may ADD. Must match CATALOG in dashboard/pet-menu.js (tests/js/test_pet_menu.js checks).
# Pages are the ids JavisNav.go() opens; "agent"/"workflow" open a tab of the Partners page, "mic" presses the mic.
KNOWN_ACTIONS = DEFAULT_ITEMS + (
    "home", "files", "learn", "conversations", "skills", "plugins", "terminal", "tasks", "webhooks",
    "mcp", "packs", "channels", "logins", "models", "settings", "share", "account", "usage", "logs",
)
# An id saved by an older Javis may no longer be known. It is kept (never lost), so it only has to look like an id.
_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,47}$")


def _ids(items):
    """The action ids of a stored item list, or None when the list is malformed or holds a duplicate."""
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        return None
    out = []
    for it in items:
        aid = it.get("actionId") if isinstance(it, dict) else None
        if not isinstance(aid, str) or not _ID_RE.match(aid) or aid in out:
            return None
        out.append(aid)
    return out


def read(settings: dict) -> dict:
    """The saved menu as the dashboard reads it.

    state "default": never customised, `items` is DEFAULT_ITEMS.
    state "custom": the owner's menu.
    state "invalid": the stored value is broken or from a newer schema. `items` is DEFAULT_ITEMS for the menu to use
    meanwhile, and the stored value is left alone: saving over it is refused (see check_save)."""
    raw = (settings or {}).get(SETTINGS_KEY)
    if raw is None:
        return {"state": "default", "rev": 0, "items": list(DEFAULT_ITEMS)}
    rev = raw.get("rev") if isinstance(raw, dict) else None
    rev = rev if isinstance(rev, int) and not isinstance(rev, bool) and rev >= 0 else 0
    if not isinstance(raw, dict) or raw.get("schemaVersion") != SCHEMA_VERSION:
        return {"state": "invalid", "rev": rev, "items": list(DEFAULT_ITEMS), "reason": "schema"}
    ids = _ids(raw.get("items"))
    if ids is None:
        return {"state": "invalid", "rev": rev, "items": list(DEFAULT_ITEMS), "reason": "items"}
    return {"state": "custom", "rev": rev, "items": ids}


def check_save(settings: dict, items, base_rev) -> tuple[str, dict | None]:
    """("", new stored value) when `items` may replace the saved menu, else (error code, None).

    Codes: "invalid_saved" (the stored value is broken: no save over it), "conflict" (edited from an older
    revision), "bad" (not a list of distinct known ids), "removed" (an item already saved is missing)."""
    cur = read(settings)
    if cur["state"] == "invalid":
        return "invalid_saved", None
    if not isinstance(base_rev, int) or isinstance(base_rev, bool) or base_rev != cur["rev"]:
        return "conflict", None
    if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
        return "bad", None
    if any(not isinstance(x, str) for x in items) or len(set(items)) != len(items):
        return "bad", None
    before = set(cur["items"])
    if not before.issubset(items):
        return "removed", None
    # Only an id the app knows may be ADDED; one already saved stays even when this Javis no longer knows it.
    if any(x not in KNOWN_ACTIONS and x not in before for x in items):
        return "bad", None
    value = {"schemaVersion": SCHEMA_VERSION, "rev": cur["rev"] + 1, "items": [{"actionId": x} for x in items]}
    return "", value
