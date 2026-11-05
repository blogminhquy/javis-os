"""The owner's own mascot menu (dashboard/pet-menu.js): which Javis features the pet opens, in which order.

Owner, 2026-11-05: "Chỉ cần thêm và sắp xếp vị trí thôi là ok rồi. Và cho phần này vào trong phần cài đặt linh vật."
So a save may only ADD features and REORDER them. Renaming, changing an icon or an action, removing and
"restore defaults" are out of scope, and this module refuses a save that would drop an item already saved.
Owner, same day: "phải có cả nút ẩn hiện nữa, để có thể ẩn bớt đi". An item can be HIDDEN instead: it stays saved
in its place (so nothing is ever lost and unhiding puts it back where it was), only the pet menu leaves it out.
At least one item stays shown, or the pet would open an empty menu.
Owner, later the same day: "phần này thêm thì có nút x để xóa chứ không phải ẩn", then "tắt luôn cả các chức năng
mặc định ... bỏ luôn cái nút mắt đi và tất cả đều là nút X, có thể tắt hết sạch được luôn". So every item, the six
defaults included, is simply removed with an X, and the menu may end up EMPTY (the pet then opens no menu). There is
no hiding any more: an item an older save flagged "hidden" reads as removed, which is what the pet already showed.
Anything removed comes back through Add feature, the defaults included.

Stored in settings.json under "pet_menu", apart from dashboard.pet: the pet's look is written on every drag of the
pet, and a stale window resending an old menu there would quietly undo a newer one. Here every save carries the
revision it was edited from, and a save made from an older revision is refused as a conflict.

    {"schemaVersion": 1, "rev": 3, "items": [{"actionId": "chat"}, {"actionId": "mic", "hidden": true}, ...]}

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


def _parse(items):
    """(ids, hidden ids) of a stored item list, or None when the list is malformed or holds a duplicate."""
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        return None
    out, hidden = [], []
    for it in items:
        aid = it.get("actionId") if isinstance(it, dict) else None
        if not isinstance(aid, str) or not _ID_RE.match(aid) or aid in out:
            return None
        flag = it.get("hidden", False)
        if not isinstance(flag, bool):
            return None
        out.append(aid)
        if flag:
            hidden.append(aid)
    return out, hidden


def read(settings: dict) -> dict:
    """The saved menu as the dashboard reads it.

    state "default": never customised, `items` is DEFAULT_ITEMS.
    state "custom": the owner's menu.
    state "invalid": the stored value is broken or from a newer schema. `items` is DEFAULT_ITEMS for the menu to use
    meanwhile, and the stored value is left alone: saving over it is refused (see check_save)."""
    raw = (settings or {}).get(SETTINGS_KEY)
    if raw is None:
        return {"state": "default", "rev": 0, "items": list(DEFAULT_ITEMS), "hidden": []}
    rev = raw.get("rev") if isinstance(raw, dict) else None
    rev = rev if isinstance(rev, int) and not isinstance(rev, bool) and rev >= 0 else 0
    if not isinstance(raw, dict) or raw.get("schemaVersion") != SCHEMA_VERSION:
        return {"state": "invalid", "rev": rev, "items": list(DEFAULT_ITEMS), "hidden": [], "reason": "schema"}
    parsed = _parse(raw.get("items"))
    if parsed is None:
        return {"state": "invalid", "rev": rev, "items": list(DEFAULT_ITEMS), "hidden": [], "reason": "items"}
    # Hidden (from 0.479.0 to 0.481.x) now means removed: the pet never showed it, the card no longer lists it.
    shown = [x for x in parsed[0] if x not in parsed[1]]
    return {"state": "custom", "rev": rev, "items": shown, "hidden": []}


def check_save(settings: dict, items, base_rev, hidden=None) -> tuple[str, dict | None]:
    """("", new stored value) when `items` may replace the saved menu, else (error code, None).

    `items` may be empty (the owner removed everything). `hidden` is still accepted from an older dashboard: those ids
    are simply left out, as removed.
    Codes: "invalid_saved" (the stored value is broken: no save over it), "conflict" (edited from an older
    revision), "bad" (not a list of distinct known ids)."""
    cur = read(settings)
    if cur["state"] == "invalid":
        return "invalid_saved", None
    if not isinstance(base_rev, int) or isinstance(base_rev, bool) or base_rev != cur["rev"]:
        return "conflict", None
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        return "bad", None
    if any(not isinstance(x, str) for x in items) or len(set(items)) != len(items):
        return "bad", None
    before = set(cur["items"])
    # Only an id the app knows may be ADDED; one already saved stays even when this Javis no longer knows it.
    if any(x not in KNOWN_ACTIONS and x not in before for x in items):
        return "bad", None
    hidden = [] if hidden is None else hidden
    if not isinstance(hidden, list) or any(not isinstance(x, str) or x not in items for x in hidden):
        return "bad", None
    hid = set(hidden)
    value = {"schemaVersion": SCHEMA_VERSION, "rev": cur["rev"] + 1,
             "items": [{"actionId": x} for x in items if x not in hid]}
    return "", value
