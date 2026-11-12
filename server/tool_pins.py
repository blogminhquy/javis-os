"""Pinned tools: the tools a brain really uses skip the search round (owner, 10/11/2026).

When a brain has many tools the hub hides them behind `javis_search_tools` and `javis_run_tool` (mcp_hub, the
lazy tier). That keeps every request small, but a tool the brain calls every day then costs one extra model round
each time: search first, then run. A round re-reads the whole context, so it is the expensive part.

This module counts which hidden tools each brain actually calls and pins the few it calls most: a pinned tool is
shown directly next to the core tools, so the model calls it at once. Everything else stays behind search.

It is one more knob of Javis Core's improvement loop (core_loop.py), not a machine of its own:

  - the KNOB is how many tools one brain may pin (`tools.pin_limit`, 0 to 8, 0 = off). The owner sets it in chat;
    a rule moves it one step when a brain has a tool waiting for a place, or when no brain fills the places.
  - the LIST of each brain follows its use, by plain code: a tool earns a place with enough recent calls and a
    real share of them, keeps it until it falls well below that bar (so the list does not flap), and loses weight
    every day it is not called. A list changes at most once a day, because the tool list sits at the front of the
    prompt and every change there costs one cold read of the provider's cache.

Bounds that no rule moves: one tool's schema may not be larger than MAX_TOOL_CHARS and all pins of a brain
together not larger than BUDGET_CHARS, so the models with the tightest quota still fit.

Performance: a tool call adds one dict update in memory. Nothing is written during a call; `tick` (every ten
minutes, in a worker thread) writes one small JSON file when something changed. No model is ever called.

Owner chat and background work of a brain share one list (a loop starts cold every time, so it gains the most);
a customer-facing bot of the same brain keeps its own, so what customers trigger does not fill the owner's list.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config import STATE_DIR

LIMIT_LO, LIMIT_HI, LIMIT_DEFAULT = 0, 8, 4
MIN_CALLS = 5.0           # weighted recent calls a tool needs before it may be pinned
MIN_SHARE = 0.03          # and at least this share of the brain's calls
KEEP_FACTOR = 0.5         # a pinned tool stays until it is under half of both bars
REPLACE_FACTOR = 2.0      # with no free place, a tool called this many times more than the weakest pin takes it
MAX_TOOL_CHARS = 2000     # one tool's name + description + schema
BUDGET_CHARS = 5000       # all pins of one brain together (about 1,400 tokens)
DECAY = 0.9               # per day: a call weighs half after about a week
REPICK_S = 24 * 3600      # a brain's list changes at most once a day
MAX_TRACKED = 120         # tools counted per brain; the least used are dropped beyond that
BOT_SUFFIX = "#bot"

_lock = threading.RLock()
_state: Dict[str, object] = {"limit": LIMIT_DEFAULT, "brains": {}}
_loaded = [False]
_dirty = [False]
# Called with {"key", "brain", "bot", "pins", "added", "removed"} when a brain's list changed. Never raises.
on_change: Optional[Callable[[dict], None]] = None


def _path() -> Path:
    return Path(STATE_DIR) / "tool-pins.json"


def key(vault_root, bot: bool = False) -> str:
    """The counter a call belongs to: one per brain, and a separate one for that brain's customer-facing bots."""
    root = str(vault_root or "").strip()
    if not root:
        return ""
    return os.path.normpath(root) + (BOT_SUFFIX if bot else "")


def brain_name(k: str) -> str:
    k = str(k or "")
    return Path(k[:-len(BOT_SUFFIX)] if k.endswith(BOT_SUFFIX) else k).name


def _load() -> None:
    if _loaded[0]:
        return
    with _lock:
        if _loaded[0]:
            return
        try:
            data = json.loads(_path().read_text(encoding="utf-8"))
            if isinstance(data, dict):
                lim = data.get("limit", LIMIT_DEFAULT)
                _state["limit"] = max(LIMIT_LO, min(LIMIT_HI, int(lim)))
                brains = data.get("brains")
                _state["brains"] = brains if isinstance(brains, dict) else {}
        except FileNotFoundError:
            pass
        except Exception as e:   # noqa: BLE001 - a broken file only means the counting starts again
            print(f"[tool pins] load: {type(e).__name__}: {e}", file=sys.stderr)
        _loaded[0] = True


def _brain(k: str) -> dict:
    brains = _state["brains"]
    b = brains.get(k)
    if not isinstance(b, dict):
        b = brains[k] = {}
    b.setdefault("runs", {})
    b.setdefault("sizes", {})
    b.setdefault("pins", [])
    return b


def note_run(k: str, fn: str, size: int = 0, direct: bool = False) -> None:
    """One call of a tool that lives behind search. direct=True: it was pinned, so no search round was needed."""
    if not k or not fn:
        return
    _load()
    with _lock:
        b = _brain(k)
        b["runs"][fn] = float(b["runs"].get(fn, 0.0)) + 1.0
        if size:
            b["sizes"][fn] = int(size)
        which = "direct" if direct else "lazy"
        b[which] = float(b.get(which, 0.0)) + 1.0
        _dirty[0] = True


def note_search(k: str) -> None:
    if not k:
        return
    _load()
    with _lock:
        b = _brain(k)
        b["searches"] = float(b.get("searches", 0.0)) + 1.0
        _dirty[0] = True


def limit() -> int:
    _load()
    return int(_state.get("limit", LIMIT_DEFAULT))


def set_limit(value) -> None:
    """Write the knob. Every brain's list is looked at again on the next tick; a lower limit applies at once."""
    _load()
    with _lock:
        _state["limit"] = max(LIMIT_LO, min(LIMIT_HI, int(value)))
        for b in _state["brains"].values():
            if isinstance(b, dict):
                b["picked"] = 0
        _dirty[0] = True


def pinned(k: str) -> Tuple[str, ...]:
    """The tools this brain shows directly, in a stable order. A memory read: safe on the chat path."""
    if not k:
        return ()
    _load()
    with _lock:
        b = _state["brains"].get(k)
        if not isinstance(b, dict):
            return ()
        return tuple((b.get("pins") or [])[:max(0, int(_state.get("limit", LIMIT_DEFAULT)))])


def pick(runs: dict, sizes: dict, current: list, lim: int) -> Tuple[List[str], str]:
    """(pins, waiting). Pure. `waiting` is the best tool that earned a place but found none free.

    Tools already pinned keep their order and new ones go to the end, so the front of the prompt changes as
    little as possible."""
    total = float(sum(runs.values()))
    if lim <= 0 or total <= 0:
        return [], ""

    def earned(fn, factor=1.0):
        n = float(runs.get(fn, 0.0))
        return n >= MIN_CALLS * factor and n / total >= MIN_SHARE * factor

    def size(fn):
        return int(sizes.get(fn) or 0)

    def fits(fn):
        return 0 < size(fn) <= MAX_TOOL_CHARS

    keep = [fn for fn in current if earned(fn, KEEP_FACTOR) and fits(fn)]
    if len(keep) > lim:
        strongest = set(sorted(keep, key=lambda f: (-float(runs.get(f, 0.0)), f))[:lim])
        keep = [fn for fn in keep if fn in strongest]
    used = sum(size(fn) for fn in keep)
    waiting = ""
    for fn in sorted(runs, key=lambda f: (-float(runs[f]), f)):
        if fn in keep or not earned(fn) or not fits(fn):
            continue
        if len(keep) < lim:
            if used + size(fn) <= BUDGET_CHARS:
                keep.append(fn)
                used += size(fn)
            continue
        weakest = min(keep, key=lambda f: (float(runs.get(f, 0.0)), f))
        if (float(runs[fn]) >= REPLACE_FACTOR * float(runs.get(weakest, 0.0))
                and used - size(weakest) + size(fn) <= BUDGET_CHARS):
            used += size(fn) - size(weakest)
            keep[keep.index(weakest)] = fn
        elif not waiting and used + size(fn) <= BUDGET_CHARS:
            waiting = fn
    return keep, waiting


def _decay(b: dict, today: int) -> None:
    last = int(b.get("day") or 0)
    if not last:
        b["day"] = today
        return
    days = today - last
    if days <= 0:
        return
    f = DECAY ** min(days, 365)
    runs = {fn: float(n) * f for fn, n in b.get("runs", {}).items() if float(n) * f >= 0.05}
    if len(runs) > MAX_TRACKED:
        runs = dict(sorted(runs.items(), key=lambda kv: -kv[1])[:MAX_TRACKED])
    b["runs"] = runs
    b["sizes"] = {fn: s for fn, s in b.get("sizes", {}).items() if fn in runs or fn in b.get("pins", [])}
    for name in ("direct", "lazy", "searches"):
        if name in b:
            b[name] = float(b[name]) * f
    b["day"] = today


def _save() -> None:
    with _lock:
        text = json.dumps(_state, ensure_ascii=False)
        _dirty[0] = False
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tool-pins-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, p)
    except Exception as e:   # noqa: BLE001 - counts lost on a failed write are counted again
        print(f"[tool pins] save: {type(e).__name__}: {e}", file=sys.stderr)


def tick(now: float = None) -> List[dict]:
    """Age the counts, look again at each brain's list when its day is over, write the file when something
    changed. Returns the list changes. Cheap: a few dict passes over at most MAX_TRACKED tools per brain."""
    _load()
    now = time.time() if now is None else now
    today = int(now // 86400)
    changes = []
    with _lock:
        lim = int(_state.get("limit", LIMIT_DEFAULT))
        for k, b in list(_state["brains"].items()):
            if not isinstance(b, dict):
                continue
            b = _brain(k)
            if int(b.get("day") or 0) != today:
                _decay(b, today)
                _dirty[0] = True
            if now - float(b.get("picked") or 0) < REPICK_S:
                continue
            old = list(b.get("pins") or [])
            new, waiting = pick(b["runs"], b["sizes"], old, lim)
            if waiting != (b.get("waiting") or ""):
                b["waiting"] = waiting
                _dirty[0] = True
            if new == old:
                continue      # nothing to change yet: keep looking, a first list should not wait a day
            b["pins"] = new
            b["picked"] = now
            _dirty[0] = True
            changes.append({"key": k, "brain": brain_name(k), "bot": k.endswith(BOT_SUFFIX), "pins": list(new),
                            "added": [fn for fn in new if fn not in old],
                            "removed": [fn for fn in old if fn not in new]})
        dirty = _dirty[0]
    if dirty:
        _save()
    if on_change:
        for ch in changes:
            try:
                on_change(ch)
            except Exception as e:   # noqa: BLE001
                print(f"[tool pins] on_change: {type(e).__name__}: {e}", file=sys.stderr)
    return changes


def limit_rule(current: int) -> Optional[tuple]:
    """The knob's rule (core_loop): one more place when a brain has a tool waiting for one, one fewer when the
    limit is above its default and no brain fills it. 0 means the owner switched pinning off: only they switch
    it back on."""
    if current <= 0:
        return None
    _load()
    with _lock:
        brains = [(k, b) for k, b in _state["brains"].items() if isinstance(b, dict)]
        waiting = [(k, b.get("waiting")) for k, b in brains if b.get("waiting")]
        most = max((len(b.get("pins") or []) for _k, b in brains), default=0)
    if waiting and current < LIMIT_HI:
        k, fn = waiting[0]
        return current + 1, f"brain {brain_name(k)} hay gọi {fn} nhưng đã hết chỗ ghim"
    if current > LIMIT_DEFAULT and most < current:
        return current - 1, "không brain nào dùng hết số chỗ ghim"
    return None


def status() -> List[dict]:
    """Per brain: what is pinned and what the counters say, for `javis_tune op=status`."""
    _load()
    out = []
    with _lock:
        lim = int(_state.get("limit", LIMIT_DEFAULT))
        for k, b in sorted(_state["brains"].items()):
            if not isinstance(b, dict):
                continue
            runs = b.get("runs") or {}
            top = sorted(runs.items(), key=lambda kv: -float(kv[1]))[:5]
            out.append({"brain": brain_name(k), "audience": "bot" if k.endswith(BOT_SUFFIX) else "owner",
                        "pinned": list((b.get("pins") or [])[:lim]),
                        "calls_direct": round(float(b.get("direct", 0.0)), 1),
                        "calls_after_search": round(float(b.get("lazy", 0.0)), 1),
                        "searches": round(float(b.get("searches", 0.0)), 1),
                        "most_called": [{"tool": fn, "calls": round(float(n), 1)} for fn, n in top]})
    return out


def reset_for_tests() -> None:
    with _lock:
        _state.clear()
        _state.update({"limit": LIMIT_DEFAULT, "brains": {}})
        _loaded[0] = True
        _dirty[0] = False
