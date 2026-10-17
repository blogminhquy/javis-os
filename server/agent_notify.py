"""Unread counts and mute for private partner chats (0.205.0).

The Teams list has had an unread count and a mute switch since 0.197.0; private partner chats on the Partners
page had neither, and the list only re-sorted when the page loaded. This store keeps, per (brain, partner):

    read_at       when the owner last had that partner's chat open (messages after it are unread)
    muted_until   0 = notifications on; a timestamp = off until then; MUTE_FOREVER = off until turned back on

The first time a partner is seen its read_at is set to now, so an existing chat history is not suddenly all
"unread" after the upgrade (same rule teams used). A muted partner's reports still land in its chat and in the bell,
filed as read and without a push (server/main.py `_bo_vao_hom_thu`).

Stored in <STATE_DIR>/agent_notify.json, small and rewritten atomically.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

FILE = "agent_notify.json"
MUTE_FOREVER = -1.0
CHOICES = ("1h", "4h", "8am", "forever", "off")


def mute_until(choice: str, now: Optional[datetime] = None) -> float:
    """The muted_until value for a menu choice. `now` is an aware datetime in the owner's time zone; "8am" means the
    next 08:00 there (tomorrow when it is already past 08:00)."""
    c = str(choice or "").strip().lower()
    if c not in CHOICES:
        raise ValueError(f"unknown mute choice: {choice}")
    if c == "off":
        return 0.0
    if c == "forever":
        return MUTE_FOREVER
    if now is None:
        now = datetime.now().astimezone()
    if c == "1h":
        return (now + timedelta(hours=1)).timestamp()
    if c == "4h":
        return (now + timedelta(hours=4)).timestamp()
    at = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if at <= now:
        at = at + timedelta(days=1)
    return at.timestamp()


def is_muted(muted_until: float, now_ts: Optional[float] = None) -> bool:
    m = float(muted_until or 0)
    if m == MUTE_FOREVER:
        return True
    return m > (time.time() if now_ts is None else now_ts)


class AgentNotify:
    def __init__(self, state_dir: Callable[[], Path], clock: Callable[[], float] = time.time):
        self._dir = state_dir
        self._clock = clock
        self._lock = threading.Lock()

    def _path(self) -> Path:
        return Path(self._dir()) / FILE

    def _load(self) -> Dict[str, dict]:
        try:
            d = json.loads(self._path().read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: Dict[str, dict]) -> None:
        p = self._path()
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".agent_notify-", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, p)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def key(brain: str, slug: str) -> str:
        return f"{brain}|{slug}"

    def records(self, brain: str, slugs: Iterable[str]) -> Dict[str, dict]:
        """{slug: {read_at, muted_until}} for these partners; a partner seen for the first time starts as read now."""
        now = self._clock()
        out: Dict[str, dict] = {}
        with self._lock:
            data = self._load()
            changed = False
            for s in slugs:
                k = self.key(brain, s)
                rec = data.get(k)
                if not isinstance(rec, dict):
                    rec = {"read_at": now, "muted_until": 0.0}
                    data[k] = rec
                    changed = True
                out[s] = {"read_at": float(rec.get("read_at") or 0), "muted_until": float(rec.get("muted_until") or 0)}
            if changed:
                self._save(data)
        return out

    def mark_read(self, brain: str, slug: str) -> float:
        now = self._clock()
        with self._lock:
            data = self._load()
            rec = data.get(self.key(brain, slug)) or {}
            rec["read_at"] = now
            rec.setdefault("muted_until", 0.0)
            data[self.key(brain, slug)] = rec
            self._save(data)
        return now

    def set_mute(self, brain: str, slug: str, until: float) -> float:
        with self._lock:
            data = self._load()
            rec = data.get(self.key(brain, slug)) or {"read_at": self._clock()}
            rec["muted_until"] = float(until)
            data[self.key(brain, slug)] = rec
            self._save(data)
        return float(until)

    def muted(self, brain: str, slug: str) -> bool:
        rec = self._load().get(self.key(brain, slug)) or {}
        return is_muted(rec.get("muted_until") or 0, self._clock())
