"""Javis Core's improvement loop: one loop, many knobs (owner, 10/11/2026).

"Propose improvements together with Javis Core so that it scales by itself, does not cost performance, and the
whole becomes a system that improves with time and with how the person uses it."

So nothing that tunes itself brings its own machinery. A part of Javis that wants to improve REGISTERS A KNOB
here: its bounds, how to read and write it, and (optionally) a rule that looks at numbers the part already
keeps and proposes one step. This module does the rest the same way for every knob:

  - a rule may move its knob one step at a time, never out of bounds, never while the owner holds it, and
    not again before a cool-down has passed (so two moves do not chase each other);
  - every move is logged with who made it and why, announced once, and can be undone by its number;
  - undoing a move holds the knob still for a while, so the same rule does not redo it the next minute;
  - a value the owner set in chat stands: no rule touches that knob for a month.

Three kinds of actor, in rising cost:
  rule   plain code looking at counters (this file's `tick`): no model, no tokens;
  core   Javis Core proposing a change after thinking, inside its own daily allowance (not built yet: it
         needs real data from the first two to be worth a model call);
  owner  what the person said in chat (`javis_tune`): always wins, and may jump more than one step.

The background scorecard (job_scorecard.py) is the first family of knobs: one per job, moved by its own rule
(`job_scorecard.step`). It keeps its own table because it moves after every run; `status` and `undo` here
show and undo both, so the owner sees one list.

Performance: `tick` runs every few minutes and only calls small functions over numbers already in memory or
in one small file; a move writes one row. Nothing here runs during a chat turn.
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import job_scorecard

ACTORS = ("rule", "core", "owner")
COOLDOWN_S = 24 * 3600            # a rule moves one knob at most once a day
HOLD_AFTER_UNDO_S = 14 * 86400    # an undone move is not tried again by a rule for two weeks
HOLD_AFTER_OWNER_S = 30 * 86400   # what the owner set by hand is left alone by every rule for a month

_lock = threading.RLock()
_KNOBS: Dict[str, "Knob"] = {}
_last_move: Dict[str, float] = {}     # knob id -> time of its last move by a rule
_held: Dict[str, float] = {}          # knob id -> a rule may not move it before this time
_loaded = [False]
# Called with a change dict when a knob moved (main.py turns it into a notice). Never raises.
on_change: Optional[Callable[[dict], None]] = None


@dataclass
class Knob:
    id: str                                        # "learn.min_turns"
    title_vi: str
    title_en: str
    lo: int
    hi: int
    default: int
    read: Callable[[], int]
    write: Callable[[int], None]
    # Looks at numbers the part already keeps and returns (new value, why) or None. Pure code.
    rule: Optional[Callable[[int], Optional[tuple]]] = None
    # True while the owner has set this by hand somewhere else: a rule then leaves it alone.
    frozen: Callable[[], bool] = lambda: False
    step: int = 1

    def clamp(self, v) -> int:
        return max(self.lo, min(self.hi, int(v)))


def register(knob: Knob) -> Knob:
    with _lock:
        _KNOBS[knob.id] = knob
    return knob


def knobs() -> List[Knob]:
    with _lock:
        return list(_KNOBS.values())


def _ensure_table() -> None:
    if _loaded[0]:
        return
    with _lock:
        if _loaded[0]:
            return
        try:
            c = job_scorecard._db()
            c.execute("CREATE TABLE IF NOT EXISTS knob_changes(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, "
                      "knob TEXT, old INTEGER, new INTEGER, actor TEXT, why TEXT, reverted REAL)")
            c.commit()
            now = time.time()
            # A restart must not let a rule move a knob it moved an hour ago, nor redo a move the owner undid.
            for knob, ts, actor, reverted in c.execute(
                    "SELECT knob, ts, actor, reverted FROM knob_changes ORDER BY id DESC LIMIT 200"):
                if actor == "rule" and knob not in _last_move:
                    _last_move[knob] = float(ts or 0)
                if reverted and float(reverted) + HOLD_AFTER_UNDO_S > now:
                    _held[knob] = max(_held.get(knob, 0), float(reverted) + HOLD_AFTER_UNDO_S)
                elif actor == "owner" and not reverted and float(ts or 0) + HOLD_AFTER_OWNER_S > now:
                    _held[knob] = max(_held.get(knob, 0), float(ts or 0) + HOLD_AFTER_OWNER_S)
        except Exception as e:   # noqa: BLE001 - a broken log must not stop the loop
            print(f"[core loop] table: {type(e).__name__}: {e}", file=sys.stderr)
        _loaded[0] = True


def change(knob_id: str, new, actor: str, why: str = "", now: float = None) -> Optional[dict]:
    """Move one knob. Returns the change, or None when nothing moved (unknown knob, same value, held, too soon).

    A rule or Javis Core moves one step; the owner may jump. The value never leaves the knob's bounds."""
    _ensure_table()
    now = time.time() if now is None else now
    k = _KNOBS.get(str(knob_id))
    if k is None or actor not in ACTORS:
        return None
    try:
        old = k.clamp(k.read())
        target = k.clamp(new)
    except Exception as e:   # noqa: BLE001
        print(f"[core loop] read {knob_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    if actor != "owner":
        if k.frozen() or _held.get(k.id, 0) > now:
            return None
        if actor == "rule" and now - _last_move.get(k.id, 0) < COOLDOWN_S:
            return None
        target = old + k.step if target > old else (old - k.step if target < old else old)
        target = k.clamp(target)
    if target == old:
        return None
    try:
        k.write(target)
    except Exception as e:   # noqa: BLE001
        print(f"[core loop] write {knob_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    ch = {"ts": now, "knob": k.id, "title_vi": k.title_vi, "title_en": k.title_en, "old": old, "new": target,
          "actor": actor, "why": str(why or "")[:300]}
    with _lock:
        if actor == "rule":
            _last_move[k.id] = now
        elif actor == "owner":
            _held[k.id] = max(_held.get(k.id, 0), now + HOLD_AFTER_OWNER_S)
        try:
            cur = job_scorecard._db().execute(
                "INSERT INTO knob_changes(ts, knob, old, new, actor, why) VALUES(?,?,?,?,?,?)",
                (now, k.id, old, target, actor, ch["why"]))
            job_scorecard._db().commit()
            ch["id"] = "k%d" % cur.lastrowid
        except Exception as e:   # noqa: BLE001
            print(f"[core loop] log: {type(e).__name__}: {e}", file=sys.stderr)
            ch["id"] = ""
    if on_change:
        try:
            on_change(ch)
        except Exception as e:   # noqa: BLE001
            print(f"[core loop] on_change: {type(e).__name__}: {e}", file=sys.stderr)
    return ch


def tick(now: float = None) -> List[dict]:
    """Let every knob's rule look at its numbers once. Cheap by contract: rules read counters, they do not scan
    history and never call a model. Returns the moves made."""
    _ensure_table()
    now = time.time() if now is None else now
    moved = []
    for k in knobs():
        if k.rule is None:
            continue
        if k.frozen() or _held.get(k.id, 0) > now or now - _last_move.get(k.id, 0) < COOLDOWN_S:
            continue
        try:
            cur = k.clamp(k.read())
            prop = k.rule(cur)
        except Exception as e:   # noqa: BLE001 - one broken rule must not stop the others
            print(f"[core loop] rule {k.id}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not prop:
            continue
        ch = change(k.id, prop[0], "rule", prop[1] if len(prop) > 1 else "", now=now)
        if ch:
            moved.append(ch)
    return moved


def undo(change_id) -> Optional[dict]:
    """Put back one move, by the number the notice gave. "k12" is a knob of this file; a plain number is a model
    change of the background scorecard. A rule then leaves that knob alone for HOLD_AFTER_UNDO_S."""
    cid = str(change_id or "").strip().lower()
    if not cid.startswith("k"):
        try:
            return job_scorecard.undo(int(cid))
        except (TypeError, ValueError):
            return None
    _ensure_table()
    try:
        num = int(cid[1:])
        with _lock:
            row = job_scorecard._db().execute(
                "SELECT knob, old, new, reverted FROM knob_changes WHERE id = ?", (num,)).fetchone()
    except Exception:   # noqa: BLE001
        return None
    if not row or row[3]:
        return None
    knob_id, old, _new, _ = row
    k = _KNOBS.get(knob_id)
    if k is None:
        return None
    now = time.time()
    try:
        k.write(k.clamp(old))
    except Exception as e:   # noqa: BLE001
        print(f"[core loop] undo {knob_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    with _lock:
        _held[knob_id] = now + HOLD_AFTER_UNDO_S
        try:
            job_scorecard._db().execute("UPDATE knob_changes SET reverted = ? WHERE id = ?", (now, num))
            job_scorecard._db().commit()
        except Exception:   # noqa: BLE001
            pass
    return {"knob": knob_id, "label": k.title_vi, "value": k.clamp(old)}


def status() -> dict:
    """Every knob with its value, bounds and recent moves, for `javis_tune op=status`."""
    _ensure_table()
    now = time.time()
    out = []
    for k in knobs():
        try:
            val = k.clamp(k.read())
        except Exception:   # noqa: BLE001
            val = k.default
        out.append({"knob": k.id, "label": k.title_vi, "value": val, "default": k.default, "min": k.lo, "max": k.hi,
                    "self_tuning": k.rule is not None and not k.frozen() and _held.get(k.id, 0) <= now})
    changes = []
    try:
        with _lock:
            for row in job_scorecard._db().execute(
                    "SELECT id, ts, knob, old, new, actor, why, reverted FROM knob_changes ORDER BY id DESC LIMIT 10"):
                d = dict(zip(("id", "ts", "knob", "old", "new", "actor", "why", "reverted"), row))
                d["id"] = "k%d" % d["id"]
                changes.append(d)
    except Exception:   # noqa: BLE001
        pass
    return {"knobs": out, "knob_changes": changes}


def reset_for_tests() -> None:
    with _lock:
        _KNOBS.clear()
        _last_move.clear()
        _held.clear()
        _loaded[0] = False
